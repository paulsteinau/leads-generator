# pipeline/generator/demo.py
"""
Generates a premium React demo website for a lead.
Flow:
  1. Scrape lead's existing website (content + screenshot)
  2. Load category reference data (cached screenshot + CSS palette)
  3. Haiku: structured content extraction (services, about, key facts)
  4. Haiku: design brief (concrete colors, fonts, layout decisions)
  5. Opus: generate App.jsx with all context + both screenshots
  6. Vite build → Vercel deploy
"""
import asyncio
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import httpx

from pipeline.scraper.website_content import scrape_website_content
from pipeline.researcher.inspiration import get_inspiration_notes, SCHEMA_TYPES
from pipeline.researcher.reference_screenshots import get_all_reference_data
from pipeline.utils.claude_p import claude_p
from pipeline.utils.skill_loader import build_design_system_prompt

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "demos"
TEMPLATE_DIR = Path(__file__).parent.parent / "react-template"
NPM_CACHE_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data")) / ".npm-cache"



def _set_sub_stage(conn, lead_id: int, sub_stage: str) -> None:
    conn.execute(
        "UPDATE leads SET demo_sub_stage=?, updated_at=datetime('now') WHERE id=?",
        (sub_stage, lead_id),
    )
    conn.commit()


def _make_slug(lead: dict) -> str:
    name = (lead.get("name") or "demo").lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")[:30]
    return f"{name}-{lead['id']}"


def _extract_structured_content(raw_text: str, subpage_text: str, category: str, conn, lead_id: int, generation_num: int = 1) -> dict:
    """Use Haiku to reliably extract services, about text, and key facts from scraped text."""
    combined = raw_text[:8000]
    if subpage_text:
        combined += f"\n\n---SUBPAGES---\n{subpage_text[:4000]}"

    is_real_estate = category in {"Immobilienmakler", "Makler"}
    is_beauty     = category in {"Friseur", "Barbier", "Kosmetik", "Kosmetikstudio", "Nagelstudio", "Massage", "Schönheitsklinik"}
    is_portfolio  = category in {"Architekt", "Fotograf", "Handwerker", "Maler", "Schreiner"}
    is_food       = category in {"Restaurant", "Cafe", "Bäckerei", "Bar"}

    if is_real_estate:
        max_tokens_extraction = 2400
    elif is_food or is_portfolio:
        max_tokens_extraction = 2000
    elif is_beauty:
        max_tokens_extraction = 1800
    else:
        max_tokens_extraction = 1600

    extra_fields = ""
    if is_real_estate:
        extra_fields += (
            "- properties: list of ALL property listing objects found in the text, each with: "
            "{\"title\": string or null, \"price\": string or null, \"size_sqm\": string or null, \"rooms\": string or null, \"type\": string or null, \"district\": string or null, \"description\": string or null}. "
            "Extract EVERY listing found — do not skip any. Return [] if none found.\n"
        )
    if is_beauty:
        extra_fields += (
            "- price_list: list of ALL services with prices found on the site, each: "
            "{\"service\": string, \"price\": string, \"duration\": string or null}. "
            "Extract every price entry. Return [] if none found.\n"
        )
    if is_portfolio:
        extra_fields += (
            "- projects: list of portfolio/project items found, each: "
            "{\"name\": string, \"type\": string or null, \"year\": string or null, \"location\": string or null, \"description\": string or null}. "
            "Max 12. Return [] if none found.\n"
        )
    if is_food:
        extra_fields += (
            "- menu_items: list of menu items/dishes found, each: "
            "{\"name\": string, \"category\": string or null, \"price\": string or null, \"description\": string or null}. "
            "Max 20. Return [] if none found.\n"
        )
    extra_fields += (
        "- team: list of named staff/team members found, each: "
        "{\"name\": string, \"title\": string, \"specialization\": string or null}. "
        "Max 8. Return [] if none found.\n"
    )

    prompt = (
        f"Extract structured information from this German {category} business website text.\n\n"
        f"Return ONLY valid JSON with these fields:\n"
        f"- services: list of strings, each a service or offering (max 10, keep original German wording)\n"
        f"- about: 2-3 sentence summary of who this business is, their story, USPs (in German)\n"
        f"- testimonials: list of customer quote strings found verbatim (max 5)\n"
        f"- phone: phone number string or null\n"
        f"- email: email address string or null\n"
        f"- opening_hours: string description if found, else null\n"
        f"- founding_year: integer year the business was founded/established, or null if not found\n"
        f"- certifications: list of strings — professional certifications, memberships, awards, quality seals, associations. Empty list if none found.\n"
        f"{extra_fields}"
        f"\nWebsite text:\n{combined}"
    )

    raw = claude_p(
        prompt=prompt,
        model="claude-sonnet-4-6",
        max_tokens=max_tokens_extraction,
        conn=conn,
        lead_id=lead_id,
        stage="content_extraction",
        generation_num=generation_num,
    )

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[^\n]*\n', '', raw)
        raw = re.sub(r'\n```$', '', raw)

    try:
        return json.loads(raw)
    except Exception:
        return {}


# Archetype pools for forced per-generation variance
_VIBE_ARCHETYPES = [
    "Ethereal Glass: deep OLED near-black (#050505), radial mesh gradients with subtle glowing accent orbs, heavy backdrop-blur cards with white/10 hairlines, wide geometric Grotesk typography",
    "Editorial Luxury: warm off-white (#FDFBF7) or deep espresso background, high-contrast display typography, subtle CSS noise/film-grain overlay (opacity 0.03), physical paper feel, editorial spacing",
    "Soft Structuralism: silver-grey or pure white background, massive bold Grotesk headlines, airy floating components with highly diffused ambient shadows, minimalist precision",
    "Dark Industrial: zinc-950 or slate-900 base, single saturated accent (electric blue OR emerald OR hot orange), mono typeface accents, sharp-edged precision, data-forward density",
    "Forest Premium: deep green + bone + amber accent, natural textures, generous whitespace, trustworthy warmth without the cliché beige-brass palette",
]
_LAYOUT_ARCHETYPES = [
    "Asymmetrical Bento: masonry-like CSS Grid of varying card sizes (col-span-8 next to stacked col-span-4), bento cells with real visual variation (images, gradients, not white-on-white)",
    "Z-Axis Cascade: elements stacked like physical cards, slightly overlapping with -2deg/3deg rotation, depth-of-field layers, scroll reveals that unfurl the stack",
    "Editorial Split: massive typography on the left half, interactive image pills or staggered cards on the right, generous negative space, editorial rhythm",
    "Sticky-Stack Scroll: hero pinned, sections stack and replace each other on scroll via GSAP ScrollTrigger, cinematic vertical storytelling",
    "Horizontal Magazine: full-width alternating sections that each use a completely different layout family (no zigzag repetition), section-by-section compositional variety",
]
_HERO_PARADIGMS = [
    "Full-Bleed Scrim Hero — edge-to-edge background image (object-fit: cover, min-h-[100dvh]), gradient scrim from bottom (rgba(0,0,0,0) → rgba(0,0,0,0.7)), bold headline + subline centered or left-aligned over image",
    "Parallax Photo Hero — full-bleed background image scrolls at 0.5x speed via GSAP/useTransform, foreground headline at 1x — cinematic depth. Image fills 100% width and 110% height to allow parallax movement",
    "Split-Overlay Hero — full-bleed background image covers entire hero, semi-transparent dark card (bg-black/50 backdrop-blur-sm) anchored to the left half contains all text. Right half shows raw image",
    "Pin-Reveal Hero — full-bleed background image, GSAP ScrollTrigger pins the hero while content sections scroll up over it revealing the image progressively from top to bottom",
    "Curtain-Reveal Hero — full-bleed background image hidden behind a solid color curtain that slides away on load (clip-path or transform), revealing the photo dramatically as the headline fades in",
]
_MOTION_LEVELS = [6, 7, 7, 8]  # weighted toward higher motion

# Animation technique pool — one per section, sampled per generation.
# tone: "formal" = Anwalt/Arzt/Notar, "neutral" = most categories, "playful" = Bar/Club/Tattoo
_ANIMATION_TECHNIQUES = [
    {
        "name": "curtain-cascade",
        "tone": ["formal", "neutral", "playful"],
        "desc": "Hero headline words stagger in from y:80 opacity:0, 120ms apart, spring ease.",
        "snippet": """\
const words = headline.split(' ');
<motion.h1>
  {words.map((word, i) => (
    <motion.span key={i} style={{display:'inline-block',marginRight:'0.25em'}}
      initial={{opacity:0, y:60}}
      animate={{opacity:1, y:0}}
      transition={{delay:i*0.12, duration:0.7, ease:[0.16,1,0.3,1]}}>
      {word}
    </motion.span>
  ))}
</motion.h1>""",
    },
    {
        "name": "slide-from-left",
        "tone": ["formal", "neutral", "playful"],
        "desc": "Element slides in from x:-80 opacity:0 on scroll entry. For images or left-side content.",
        "snippet": """\
<motion.div
  initial={{opacity:0, x:-80}}
  whileInView={{opacity:1, x:0}}
  viewport={{once:true, amount:0.3}}
  transition={{duration:0.7, ease:[0.16,1,0.3,1]}}>
  {/* image or content block */}
</motion.div>""",
    },
    {
        "name": "slide-from-right",
        "tone": ["formal", "neutral", "playful"],
        "desc": "Element slides in from x:80 opacity:0 on scroll entry. For images or right-side content.",
        "snippet": """\
<motion.div
  initial={{opacity:0, x:80}}
  whileInView={{opacity:1, x:0}}
  viewport={{once:true, amount:0.3}}
  transition={{duration:0.7, ease:[0.16,1,0.3,1]}}>
  {/* image or content block */}
</motion.div>""",
    },
    {
        "name": "text-scrub-reveal",
        "tone": ["formal", "neutral"],
        "desc": "GSAP ScrollTrigger: paragraph writes itself word-by-word as user scrolls through the section.",
        "snippet": """\
// Wrap each word in a span with className="scrub-word"
useEffect(() => {
  const ctx = gsap.context(() => {
    gsap.fromTo('.scrub-word',
      {opacity:0.08},
      {opacity:1, stagger:0.05,
       scrollTrigger:{trigger:'.scrub-section',start:'top 70%',end:'bottom 30%',scrub:1}});
  });
  return () => ctx.revert();
}, []);
// JSX: <p className="scrub-section">{text.split(' ').map((w,i)=><span key={i} className="scrub-word">{w} </span>)}</p>""",
    },
    {
        "name": "typewriter",
        "tone": ["neutral", "playful"],
        "desc": "Characters appear one-by-one as if typed live, with a blinking cursor.",
        "snippet": """\
const [displayed, setDisplayed] = useState('');
const fullText = 'Your headline here'; // replace with actual text
useEffect(() => {
  let i = 0;
  const id = setInterval(() => {
    setDisplayed(fullText.slice(0, ++i));
    if (i >= fullText.length) clearInterval(id);
  }, 55);
  return () => clearInterval(id);
}, []);
// JSX: <h1>{displayed}<span style={{animation:'blink 1s step-end infinite'}}>|</span></h1>
// CSS: @keyframes blink{0%,100%{opacity:1}50%{opacity:0}}""",
    },
    {
        "name": "clip-path-wipe",
        "tone": ["formal", "neutral", "playful"],
        "desc": "Horizontal wipe: clip-path inset(0 100% 0 0) → inset(0 0 0 0) reveals image or block.",
        "snippet": """\
<motion.div
  initial={{clipPath:'inset(0 100% 0 0)'}}
  whileInView={{clipPath:'inset(0 0% 0 0)'}}
  viewport={{once:true, amount:0.4}}
  transition={{duration:0.9, ease:[0.32,0.72,0,1]}}>
  {/* image or content block */}
</motion.div>""",
    },
    {
        "name": "spring-pop",
        "tone": ["neutral", "playful"],
        "desc": "Cards scale from 0.85+opacity:0 with spring physics, staggered 80ms.",
        "snippet": """\
const container = {hidden:{}, show:{transition:{staggerChildren:0.08}}};
const item = {
  hidden:{opacity:0, scale:0.85},
  show:{opacity:1, scale:1, transition:{type:'spring',duration:0.5,bounce:0.2}}
};
<motion.div variants={container} initial="hidden" whileInView="show" viewport={{once:true}}>
  {cards.map((c,i) => <motion.div key={i} variants={item}>{/* card */}</motion.div>)}
</motion.div>""",
    },
    {
        "name": "gsap-pin-text",
        "tone": ["formal", "neutral"],
        "desc": "Section heading pins on one side (GSAP pin:true) while cards/text scroll past on the other.",
        "snippet": """\
useEffect(() => {
  const ctx = gsap.context(() => {
    ScrollTrigger.create({
      trigger:'.pin-section', start:'top top', end:'bottom bottom',
      pin:'.pin-left', pinSpacing:false,
    });
  });
  return () => ctx.revert();
}, []);
// JSX: <div className="pin-section flex min-h-[200vh]">
//   <div className="pin-left w-1/2 h-screen sticky top-0 flex items-center">heading</div>
//   <div className="w-1/2">{scrolling content}</div>
// </div>""",
    },
    {
        "name": "parallax-layers",
        "tone": ["formal", "neutral", "playful"],
        "desc": "Background moves at 0.3x scroll speed, foreground text at 0.7x — depth parallax.",
        "snippet": """\
const ref = useRef(null);
const {scrollYProgress} = useScroll({target:ref, offset:['start end','end start']});
const bgY = useTransform(scrollYProgress, [0,1], ['0%','30%']);
const fgY = useTransform(scrollYProgress, [0,1], ['0%','-15%']);
// JSX:
<section ref={ref} style={{overflow:'hidden', position:'relative', minHeight:'100dvh'}}>
  <motion.div style={{y:bgY, position:'absolute', inset:0, zIndex:0}}>
    <img src={bgImg} style={{width:'100%',height:'120%',objectFit:'cover'}} />
  </motion.div>
  <motion.div style={{y:fgY, position:'relative', zIndex:1, padding:'8rem 2rem'}}>
    {/* headline and text */}
  </motion.div>
</section>""",
    },
    {
        "name": "blur-emerge",
        "tone": ["formal", "neutral"],
        "desc": "Elements enter from blur(12px)+y:40+opacity:0 → sharp — focus-pull effect.",
        "snippet": """\
<motion.div
  initial={{opacity:0, y:40, filter:'blur(12px)'}}
  whileInView={{opacity:1, y:0, filter:'blur(0px)'}}
  viewport={{once:true, amount:0.3}}
  transition={{duration:0.8, ease:[0.16,1,0.3,1]}}>
  {/* content */}
</motion.div>""",
    },
    {
        "name": "count-up",
        "tone": ["formal", "neutral", "playful"],
        "desc": "Numbers animate from 0 to final value over 1200ms via IntersectionObserver.",
        "snippet": """\
function CountUp({end, suffix=''}) {
  const [val, setVal] = useState(0);
  const ref = useRef(null);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      let cur = 0; const step = end / 60;
      const t = setInterval(() => {
        cur += step;
        if (cur >= end) { setVal(end); clearInterval(t); return; }
        setVal(Math.floor(cur));
      }, 20);
      obs.disconnect();
    }, {threshold:0.5});
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [end]);
  return <span ref={ref}>{val}{suffix}</span>;
}
// Usage: <CountUp end={127} suffix=" Kunden" />""",
    },
    {
        "name": "horizontal-marquee",
        "tone": ["neutral", "playful"],
        "desc": "Infinite CSS loop: items scroll horizontally. For reviews, logos, or service tags.",
        "snippet": """\
// Add to <style> tag: @keyframes marquee{from{transform:translateX(0)}to{transform:translateX(-50%)}}
<div style={{overflow:'hidden', width:'100%'}}>
  <div style={{display:'flex', width:'max-content',
    animation:'marquee 30s linear infinite'}}>
    {[...items, ...items].map((item, i) => (
      <div key={i} style={{flexShrink:0, padding:'0 2.5rem'}}>{item}</div>
    ))}
  </div>
</div>""",
    },
    {
        "name": "alternating-slide",
        "tone": ["formal", "neutral", "playful"],
        "desc": "Odd rows from x:-80, even from x:80 — zigzag entry rhythm across the section.",
        "snippet": """\
{items.map((item, i) => (
  <motion.div key={i}
    initial={{opacity:0, x: i % 2 === 0 ? -80 : 80}}
    whileInView={{opacity:1, x:0}}
    viewport={{once:true, amount:0.3}}
    transition={{duration:0.7, ease:[0.16,1,0.3,1]}}>
    {/* item content */}
  </motion.div>
))}""",
    },
    {
        "name": "gsap-card-stack",
        "tone": ["formal", "neutral"],
        "desc": "GSAP: cards pin and layer on top of each other as user scrolls down.",
        "snippet": """\
useEffect(() => {
  const ctx = gsap.context(() => {
    gsap.utils.toArray('.stack-card').forEach((card, i) => {
      ScrollTrigger.create({
        trigger: card,
        start: `top ${60 - i * 5}px`,
        end: 'max',
        pin: true,
        pinSpacing: false,
      });
    });
  });
  return () => ctx.revert();
}, []);
// JSX: each card needs className="stack-card" and style={{zIndex: i+1}}""",
    },
    {
        "name": "scale-reveal",
        "tone": ["formal", "neutral", "playful"],
        "desc": "Image scale:1.15→1.0 inside overflow-hidden — zoom-into-frame on scroll entry.",
        "snippet": """\
<div style={{overflow:'hidden', borderRadius:'1rem'}}>
  <motion.img src={src} alt={alt}
    initial={{scale:1.15}}
    whileInView={{scale:1.0}}
    viewport={{once:true, amount:0.3}}
    transition={{duration:1.0, ease:[0.16,1,0.3,1]}}
    style={{width:'100%', height:'100%', objectFit:'cover', display:'block'}} />
</div>""",
    },
]

# Traditional professions where serif headings are appropriate
_SERIF_CATEGORIES = {"Anwalt", "Rechtsanwalt", "Notar", "Arzt", "Zahnarzt", "Steuerberater", "Architekt"}
# Professions that suit a light/clean background (not dark OLED by default)
_LIGHT_MODE_CATEGORIES = {"Zahnarzt", "Physiotherapeut", "Kosmetik", "Optiker", "Apotheke", "Kinderarzt", "Hebamme"}
# Professions that suit a dark/moody background
_DARK_MODE_CATEGORIES = {"Bar", "Restaurant", "Club", "DJ", "Fotograf", "Tattoo", "Barbier"}

# Category → animation tone mapping
# formal: restrained, no gimmicks (Anwalt, Arzt, Notar, Steuerberater, Architekt, Immobilien)
# playful: energy, bounce OK (Bar, Club, Tattoo, DJ, Fotograf, Barbier, Florist)
# neutral: anything else — full pool
_FORMAL_CATEGORIES = {"Anwalt", "Rechtsanwalt", "Notar", "Arzt", "Steuerberater", "Architekt",
                      "Immobilienmakler", "Unternehmensberater", "Wirtschaftsprüfer", "Notariat",
                      # Medical — professional, calm, trust-building; no playful animations
                      "Zahnarzt", "Kinderarzt", "Physiotherapeut", "Apotheke", "Hebamme", "Optiker"}
_PLAYFUL_CATEGORIES = {"Bar", "Club", "DJ", "Tattoo", "Fotograf", "Barbier",
                       "Florist", "Eventplaner", "Partyservice"}


def _pick_animations(category: str, k: int = 6) -> list:
    """Sample k animation techniques appropriate for the business category."""
    if category in _FORMAL_CATEGORIES:
        tone = "formal"
    elif category in _PLAYFUL_CATEGORIES:
        tone = "playful"
    else:
        tone = "neutral"
    pool = [t for t in _ANIMATION_TECHNIQUES if tone in t["tone"]]
    # Fallback: if pool too small, open up to neutral
    if len(pool) < k:
        pool = [t for t in _ANIMATION_TECHNIQUES if "neutral" in t["tone"]]
    return random.sample(pool, k=min(k, len(pool)))


# ── Curated premium palettes ──────────────────────────────────────────────────
# Each entry: bg, surface, text, accent, shadow — all hex, all calibrated.
# Formal = Anwalt/Notar/Steuerberater/Architekt. Medical = Arzt/Zahnarzt/etc.
# Light-trade = Kosmetik/Optiker/Hebamme. Playful = Bar/Club/Tattoo.
# "neutral" categories get no forced palette — brief decides freely.

_PALETTES_FORMAL = [
    # Dark — legal / finance / authority
    {"name": "Legal Navy",        "bg": "#080f1a", "surface": "#0d1a2e", "text": "#f0ebe0", "accent": "#c4a35a", "shadow": "#030810"},
    {"name": "Charcoal Edit",     "bg": "#111111", "surface": "#1c1c1c", "text": "#e8e4db", "accent": "#a08060", "shadow": "#080808"},
    {"name": "Midnight Slate",    "bg": "#0d1017", "surface": "#151b26", "text": "#dde4ee", "accent": "#7a9ab8", "shadow": "#060810"},
    {"name": "Deep Burgundy",     "bg": "#130a0c", "surface": "#1e1014", "text": "#f0e8ea", "accent": "#a05060", "shadow": "#080508"},
    {"name": "Dark Espresso",     "bg": "#100d0a", "surface": "#1a1612", "text": "#ede8e0", "accent": "#c08850", "shadow": "#080603"},
    {"name": "Graphite Authority","bg": "#0e0e0f", "surface": "#191919", "text": "#e0ddd8", "accent": "#8899aa", "shadow": "#070708"},
    # Light — editorial / prestigious
    {"name": "Barrister Ivory",   "bg": "#f6f2eb", "surface": "#ffffff", "text": "#161410", "accent": "#7a5c2e", "shadow": "#ddd8cc"},
    {"name": "Forest Authority",  "bg": "#0c1a12", "surface": "#132318", "text": "#edf0e8", "accent": "#8aab7a", "shadow": "#060d08"},
    {"name": "Warm Parchment",    "bg": "#f5f0e6", "surface": "#fffcf5", "text": "#1a150e", "accent": "#6b5040", "shadow": "#ddd5c4"},
    {"name": "Stone Editorial",   "bg": "#f2f2f0", "surface": "#ffffff", "text": "#181818", "accent": "#607060", "shadow": "#d8d8d4"},
    {"name": "Cool Linen",        "bg": "#f4f5f7", "surface": "#ffffff", "text": "#141820", "accent": "#4a5c70", "shadow": "#d8dce4"},
    {"name": "Dusty Rose Law",    "bg": "#f7f3f2", "surface": "#ffffff", "text": "#1c1614", "accent": "#8c5860", "shadow": "#e0d8d4"},
]

_PALETTES_MEDICAL = [
    # Light — clinical / trustworthy
    {"name": "Clinical Light",   "bg": "#f8fafc", "surface": "#ffffff", "text": "#0f1e30", "accent": "#2c6e8a", "shadow": "#d4e0ea"},
    {"name": "Warm Care",        "bg": "#fdfaf5", "surface": "#ffffff", "text": "#1c1812", "accent": "#4e7a6a", "shadow": "#e4ddd0"},
    {"name": "Sage Practice",    "bg": "#f4f7f4", "surface": "#ffffff", "text": "#141e18", "accent": "#3d7060", "shadow": "#d8e4dc"},
    {"name": "Pearl Clinic",     "bg": "#f9f8f6", "surface": "#ffffff", "text": "#161410", "accent": "#5a6e80", "shadow": "#e0dcd4"},
    {"name": "Soft Teal Health", "bg": "#f4f9f8", "surface": "#ffffff", "text": "#0f1e1c", "accent": "#3a7870", "shadow": "#d4e8e4"},
    {"name": "Blush Wellness",   "bg": "#fdf6f5", "surface": "#ffffff", "text": "#1e1614", "accent": "#8a5a60", "shadow": "#e8d8d4"},
    # Dark — premium specialist (physio, optiker — NOT for dental/family medicine)
    {"name": "Deep Medical",     "bg": "#0a1520", "surface": "#0f2030", "text": "#e8f0f8", "accent": "#4ab8c8", "shadow": "#050c14"},
    {"name": "Midnight Teal",    "bg": "#081410", "surface": "#0e2018", "text": "#e4f0ec", "accent": "#50b890", "shadow": "#040a08"},
    {"name": "Dark Slate Health","bg": "#0c1018", "surface": "#131b28", "text": "#dce8f0", "accent": "#608898", "shadow": "#060810"},
]

# Dental-specific palettes — LIGHT ONLY. Zahnarzt must never get dark/navy.
# Warm whites, soft teals, sage greens, blush — never cold dark blue.
_PALETTES_DENTAL = [
    {"name": "Pearl Smile",      "bg": "#ffffff",  "surface": "#f7fbfd", "text": "#0f1c28", "accent": "#3a8a9a", "shadow": "#cce4ec"},
    {"name": "Warm Dental",      "bg": "#fdfaf5",  "surface": "#ffffff", "text": "#1c1812", "accent": "#4e7a6a", "shadow": "#dde8e4"},
    {"name": "Soft Mint",        "bg": "#f4f8f6",  "surface": "#ffffff", "text": "#121c18", "accent": "#3a7860", "shadow": "#cce0d8"},
    {"name": "Cloud Clinic",     "bg": "#f8f9fb",  "surface": "#ffffff", "text": "#141c24", "accent": "#5a7890", "shadow": "#d4dce8"},
    {"name": "Ivory Practice",   "bg": "#fdf9f4",  "surface": "#ffffff", "text": "#1a1610", "accent": "#8a7060", "shadow": "#e8ddd4"},
    {"name": "Blush Clinical",   "bg": "#fdf6f5",  "surface": "#ffffff", "text": "#1c1614", "accent": "#8a5a6a", "shadow": "#ecdce0"},
]

_PALETTES_LIGHT_TRADE = [
    {"name": "Soft Studio",      "bg": "#faf8f5", "surface": "#ffffff", "text": "#1c1814", "accent": "#9b6e5c", "shadow": "#e4ddd6"},
    {"name": "Clean Nordic",     "bg": "#f5f7f8", "surface": "#ffffff", "text": "#141c24", "accent": "#5c7a8a", "shadow": "#d8e0e8"},
    {"name": "Warm Craft",       "bg": "#fdf8f2", "surface": "#ffffff", "text": "#1e1810", "accent": "#8c6840", "shadow": "#e8e0d4"},
    {"name": "Blush Atelier",    "bg": "#fdf5f4", "surface": "#ffffff", "text": "#1e1614", "accent": "#c07080", "shadow": "#ecdcd8"},
    {"name": "Sage Workshop",    "bg": "#f4f6f2", "surface": "#ffffff", "text": "#141c10", "accent": "#6a8460", "shadow": "#d8e0d0"},
    {"name": "Terracotta Studio","bg": "#faf5f0", "surface": "#ffffff", "text": "#1c1610", "accent": "#a07060", "shadow": "#e8ddd4"},
    {"name": "Dusty Lavender",   "bg": "#f6f4f8", "surface": "#ffffff", "text": "#16141c", "accent": "#7868a0", "shadow": "#e0dce8"},
    {"name": "Dark Craft",       "bg": "#0f0d0b", "surface": "#1a1714", "text": "#f0ece4", "accent": "#c89060", "shadow": "#070503"},
]

_PALETTES_PLAYFUL = [
    {"name": "Ink Dark",         "bg": "#0a0a0c", "surface": "#131318", "text": "#f0eeea", "accent": "#e85c3a", "shadow": "#050508"},
    {"name": "Studio Night",     "bg": "#0f0e14", "surface": "#1a1824", "text": "#eceaf8", "accent": "#9b70e0", "shadow": "#08070e"},
    {"name": "Raw Industrial",   "bg": "#111110", "surface": "#1c1c1a", "text": "#f0ede6", "accent": "#d4a030", "shadow": "#080806"},
    {"name": "Deep Crimson",     "bg": "#0e0a0a", "surface": "#1c1212", "text": "#f4ede8", "accent": "#c43030", "shadow": "#080404"},
    {"name": "Electric Moss",    "bg": "#090c08", "surface": "#121a10", "text": "#eef4e8", "accent": "#70c840", "shadow": "#050804"},
    {"name": "Neon Night",       "bg": "#08090f", "surface": "#10121c", "text": "#eeeef8", "accent": "#3060e8", "shadow": "#050608"},
    {"name": "Warm Amber Bar",   "bg": "#0e0b06", "surface": "#1c1810", "text": "#f4eedc", "accent": "#e09030", "shadow": "#070504"},
    {"name": "Deep Violet",      "bg": "#0c0810", "surface": "#180f20", "text": "#ece8f8", "accent": "#b040d0", "shadow": "#080510"},
]

_CATEGORY_TO_PALETTE_BUCKET = {
    # formal
    "Anwalt": _PALETTES_FORMAL, "Rechtsanwalt": _PALETTES_FORMAL,
    "Notar": _PALETTES_FORMAL, "Notariat": _PALETTES_FORMAL,
    "Steuerberater": _PALETTES_FORMAL, "Wirtschaftsprüfer": _PALETTES_FORMAL,
    "Unternehmensberater": _PALETTES_FORMAL, "Immobilienmakler": _PALETTES_FORMAL,
    "Architekt": _PALETTES_FORMAL,
    # medical
    "Arzt": _PALETTES_MEDICAL, "Kinderarzt": _PALETTES_DENTAL,
    "Zahnarzt": _PALETTES_DENTAL, "Physiotherapeut": _PALETTES_MEDICAL,
    "Apotheke": _PALETTES_MEDICAL, "Hebamme": _PALETTES_MEDICAL,
    "Optiker": _PALETTES_MEDICAL,
    # light trade
    "Kosmetik": _PALETTES_LIGHT_TRADE, "Kosmetikstudio": _PALETTES_LIGHT_TRADE,
    "Nagelstudio": _PALETTES_LIGHT_TRADE, "Friseur": _PALETTES_LIGHT_TRADE,
    "Massage": _PALETTES_LIGHT_TRADE,
    # playful
    "Bar": _PALETTES_PLAYFUL, "Club": _PALETTES_PLAYFUL, "DJ": _PALETTES_PLAYFUL,
    "Tattoo": _PALETTES_PLAYFUL, "Fotograf": _PALETTES_PLAYFUL,
    "Barbier": _PALETTES_PLAYFUL, "Florist": _PALETTES_PLAYFUL,
    "Eventplaner": _PALETTES_PLAYFUL, "Partyservice": _PALETTES_PLAYFUL,
}


# Per-category style profiles — controls animation count, image mood, and artistic direction
# k_animations: how many animation techniques to assign (less = more restrained)
# image_mood: what Picsum seeds and CSS filters to use, injected into brief
# richness: "editorial" | "balanced" | "showcase" | "expressive" — overall visual density
# section_emphasis: which sections to visually amplify (injected as brief note)
_CATEGORY_STYLE_PROFILES: dict[str, dict] = {
    # ── Legal / finance — restrained editorial, quality over quantity ─────────
    "Anwalt":            {"k": 4, "richness": "editorial",  "image_mood": "architectural textures, law books, stone facades, natural light through windows — NO stock handshakes or people in suits", "section_emphasis": "Hero + Leistungen (biggest impact), Kontakt (clean form)"},
    "Rechtsanwalt":      {"k": 4, "richness": "editorial",  "image_mood": "architectural textures, law books, stone facades, natural light through windows — NO stock handshakes or people in suits", "section_emphasis": "Hero + Leistungen (biggest impact), Kontakt (clean form)"},
    "Notar":             {"k": 4, "richness": "editorial",  "image_mood": "close-up of stamps, official documents, marble surfaces, pen on paper", "section_emphasis": "Hero (authoritative), Leistungen (structured list), Über uns"},
    "Notariat":          {"k": 4, "richness": "editorial",  "image_mood": "close-up of stamps, official documents, marble surfaces, pen on paper", "section_emphasis": "Hero (authoritative), Leistungen"},
    "Steuerberater":     {"k": 4, "richness": "editorial",  "image_mood": "clean desk, calculator, financial charts, minimal office — precise and trustworthy", "section_emphasis": "Hero + Leistungen + Über uns"},
    "Wirtschaftsprüfer": {"k": 4, "richness": "editorial",  "image_mood": "boardroom, data visualization, clean architecture — serious and capable", "section_emphasis": "Hero + Leistungen"},
    "Unternehmensberater":{"k": 5,"richness": "balanced",   "image_mood": "strategy sessions, whiteboards, city skyline, modern office — energetic but credible", "section_emphasis": "Hero + Leistungen + Stats/Zahlen"},
    # ── Architekt — editorial but with strong portfolio emphasis ──────────────
    "Architekt":         {"k": 5, "richness": "showcase",   "image_mood": "architectural photography, building details, clean geometry, construction materials — dramatic angles", "section_emphasis": "Hero (full-bleed project photo), Projekte gallery (largest section), Über uns"},
    # ── Real estate — image-first, interactive property gallery mandatory ────
    "Immobilienmakler":  {"k": 6, "richness": "showcase",   "image_mood": "beautiful property interiors, wide-angle living rooms, kitchen close-ups, architectural exteriors, city skylines, natural light flooding rooms — every section uses large property images, NEVER generic business stock", "section_emphasis": "Hero (full-bleed property photo MANDATORY), Angebote gallery (LARGEST section — interactive image grid or carousel showing multiple properties with photos), Leistungen, Über uns (team photo), Kontakt — images dominate text in every section"},
    # ── Medical — clean clinical, calm visuals ────────────────────────────────
    "Arzt":              {"k": 4, "richness": "balanced",   "image_mood": "calm clinic interiors, soft light, medical equipment close-ups — NO cheesy stock doctors", "section_emphasis": "Hero (calm, reassuring), Leistungen, Über uns (doctor portrait only if real photo available)"},
    "Kinderarzt":        {"k": 4, "richness": "balanced",   "image_mood": "bright warm clinic, soft toys, natural light, friendly space — warm not clinical", "section_emphasis": "Hero (warm and welcoming), Leistungen"},
    "Zahnarzt":          {"k": 4, "richness": "balanced",   "image_mood": "modern dental equipment close-ups, clean white surfaces, soft light — sleek not sterile", "section_emphasis": "Hero + Leistungen + Bewertungen (trust-building)"},
    "Physiotherapeut":   {"k": 5, "richness": "balanced",   "image_mood": "treatment room, exercise equipment, natural light, movement — active and human", "section_emphasis": "Hero + Leistungen + Über uns"},
    "Apotheke":          {"k": 4, "richness": "balanced",   "image_mood": "pharmacy shelves, pill close-ups, clean counters, friendly space", "section_emphasis": "Hero + Leistungen + Kontakt"},
    "Hebamme":           {"k": 4, "richness": "balanced",   "image_mood": "warm soft tones, natural textiles, calm home setting — intimate and reassuring", "section_emphasis": "Hero (warm), Leistungen, Über uns"},
    "Optiker":           {"k": 5, "richness": "showcase",   "image_mood": "eyewear product shots, optical precision details, brand lifestyle — boutique feel", "section_emphasis": "Hero (product), Sortiment gallery, Über uns"},
    # ── Trades / Handwerk — process + results, before/after ──────────────────
    "Handwerker":        {"k": 5, "richness": "showcase",   "image_mood": "close-up of hands at work, finished projects, raw materials, tools — authentic craft", "section_emphasis": "Hero (project photo), Leistungen, Projekte gallery (before/after if available)"},
    "Maler":             {"k": 5, "richness": "showcase",   "image_mood": "freshly painted walls with dramatic light, paint textures, color swatches, finished rooms — vivid and clean", "section_emphasis": "Hero (color-rich project), Projekte gallery (dominant section), Leistungen"},
    "Elektriker":        {"k": 4, "richness": "balanced",   "image_mood": "electrical panels, wiring close-ups, modern smart-home tech, precision tools — technical trustworthy", "section_emphasis": "Hero + Leistungen + Kontakt (emergency emphasis)"},
    "Sanitär":           {"k": 4, "richness": "balanced",   "image_mood": "modern bathroom installations, copper pipes, premium fixtures — clean and precise", "section_emphasis": "Hero + Leistungen + Kontakt"},
    "Schreiner":         {"k": 5, "richness": "showcase",   "image_mood": "wood grain close-ups, finished furniture, workshop tools, natural materials — warm craft quality", "section_emphasis": "Hero + Projekte gallery + Leistungen"},
    "Klempner":          {"k": 4, "richness": "balanced",   "image_mood": "clean modern bathrooms, copper pipes, precision fittings — reliable and professional", "section_emphasis": "Hero + Leistungen + Kontakt (24h emergency)"},
    # ── Beauty / wellness — lifestyle, product, atmosphere ───────────────────
    "Kosmetik":          {"k": 5, "richness": "expressive", "image_mood": "skincare textures, clean product flatlays, glowing skin close-ups, warm studio light — aspirational", "section_emphasis": "Hero (atmosphere), Leistungen, Bewertungen, Kontakt"},
    "Kosmetikstudio":    {"k": 5, "richness": "expressive", "image_mood": "studio interior, treatment products, serene lighting — premium spa feel", "section_emphasis": "Hero + Leistungen + Über uns"},
    "Nagelstudio":       {"k": 5, "richness": "expressive", "image_mood": "nail art close-ups, product textures, pastel studio interior — detail-oriented and aesthetic", "section_emphasis": "Hero + Galerie (nail work) + Leistungen"},
    "Friseur":           {"k": 5, "richness": "expressive", "image_mood": "salon interior, hair color transformations, product shots, styling — vibrant and creative", "section_emphasis": "Hero (dramatic styling shot) + Leistungen + Galerie"},
    "Massage":           {"k": 4, "richness": "balanced",   "image_mood": "spa stones, warm candlelight, towels, zen interior — tranquil and sensory", "section_emphasis": "Hero (atmosphere) + Leistungen + Buchung CTA"},
    # ── Playful / creative / nightlife ───────────────────────────────────────
    "Bar":               {"k": 6, "richness": "expressive", "image_mood": "cocktail photography, moody bar lighting, spirit bottles, atmospheric crowd shots — cinematic dark", "section_emphasis": "Hero (full-bleed atmosphere) + Karte/Menu + Events"},
    "Club":              {"k": 6, "richness": "expressive", "image_mood": "dark venue with dramatic lighting, DJ setup, crowd energy, laser lights — cinematic night", "section_emphasis": "Hero (full atmosphere) + Events + Location"},
    "DJ":                {"k": 6, "richness": "expressive", "image_mood": "DJ equipment close-up, stage atmosphere, crowd energy, audio waveforms — high energy", "section_emphasis": "Hero + Mix/Work gallery + Buchung"},
    "Tattoo":            {"k": 6, "richness": "expressive", "image_mood": "tattoo close-ups showing craft, studio interior, ink supplies, artist at work — dark and artistic", "section_emphasis": "Hero + Galerie (dominant — max portfolio shots) + Stile + Kontakt"},
    "Fotograf":          {"k": 6, "richness": "expressive", "image_mood": "USE REAL scraped images as primary — show photography portfolio; Picsum only as fallback", "section_emphasis": "Hero (best portfolio shot) + Portfolio gallery (dominant) + Leistungen + Kontakt"},
    "Barbier":           {"k": 5, "richness": "expressive", "image_mood": "razor and barber tools, masculine grooming products, barber shop interior — artisanal dark aesthetic", "section_emphasis": "Hero (dark atmospheric) + Leistungen + Team"},
    "Florist":           {"k": 6, "richness": "expressive", "image_mood": "flower close-ups with shallow depth of field, arrangement process, studio with natural light — lush and colorful", "section_emphasis": "Hero (flowers full-bleed) + Galerie + Leistungen + Kontakt"},
    "Eventplaner":       {"k": 6, "richness": "expressive", "image_mood": "beautifully decorated event venues, table settings, floral arrangements, ambient lighting — aspirational", "section_emphasis": "Hero + Referenzen gallery + Leistungen + Kontakt"},
    "Partyservice":      {"k": 5, "richness": "expressive", "image_mood": "food spreads, event atmosphere, catering setup, happy crowds — festive energy", "section_emphasis": "Hero + Leistungen + Galerie + Kontakt"},
    # ── Restaurants / food ───────────────────────────────────────────────────
    "Restaurant":        {"k": 5, "richness": "expressive", "image_mood": "food photography (top-down dishes), restaurant interior, chef at work, plating details", "section_emphasis": "Hero (signature dish) + Karte highlights + Atmosphäre + Reservierung CTA"},
    "Cafe":              {"k": 5, "richness": "expressive", "image_mood": "latte art, pastry close-ups, warm cafe interior, morning light — cozy and inviting", "section_emphasis": "Hero + Karte + Atmosphäre + Standort"},
    "Bäckerei":          {"k": 5, "richness": "expressive", "image_mood": "bread close-ups, bakery process, flour dusted hands, oven light — authentic craft", "section_emphasis": "Hero + Sortiment + Über uns + Standort"},
}

_DEFAULT_STYLE_PROFILE = {"k": 5, "richness": "balanced", "image_mood": "authentic business photography — real materials, real spaces, no generic stock", "section_emphasis": "Hero + Leistungen + Kontakt"}


def _get_style_profile(category: str) -> dict:
    return _CATEGORY_STYLE_PROFILES.get(category, _DEFAULT_STYLE_PROFILE)


def _get_suggested_palette(category: str, seed: str = "") -> dict | None:
    """Pick a palette deterministically from the category bucket.

    Uses a hash of `seed` (business name or URL) so the same business always
    gets the same palette, but different businesses in the same category get
    visually distinct ones.
    """
    bucket = _CATEGORY_TO_PALETTE_BUCKET.get(category)
    if not bucket:
        return None
    idx = int(hashlib.md5(seed.encode("utf-8", errors="ignore")).hexdigest(), 16) % len(bucket)
    return bucket[idx]


# Formal-category premium design rules injected into the brief prompt
_FORMAL_PREMIUM_RULES = """
FORMAL PROFESSION — PREMIUM DESIGN RULES (non-negotiable):
- Typography: serif heading (Fraunces, Playfair Display, Cormorant Garamond, or Lora) + clean sans body (DM Sans, Inter, Outfit). No sans-only pairing.
- Color: use the SUGGESTED PALETTE above exactly. If a scraped brand color exists, anchor one value to it — but stay within the palette's mood. Accent must be muted (bronze, sage, steel, rose-gold) — NEVER neon, AI-purple, or sky-blue.
- UNIQUENESS RULE: NEVER default to navy background + gold accent for legal/formal sites — that is the generic AI cliche. The suggested palette was chosen specifically for this business. Use it. If the palette is dark burgundy, use burgundy. If it's stone editorial, use stone.
- Imagery: architectural detail shots, texture close-ups, material photography. NO generic smiling stock people, NO generic handshake photos.
- Layout: editorial and asymmetric. No equal-column feature grids, no bento chaos. Clean hierarchy, generous whitespace.
- Radius: SHARP tier only. Cards max rounded-xl (12px). Images max rounded-lg (8px) or no rounding. Inputs rounded-md. NEVER rounded-2xl, rounded-3xl, rounded-[2rem] or larger — those radii belong on consumer apps, not professional service firms.
- Motion: restrained — blur-emerge, text-scrub, gsap-pin-text, scale-reveal preferred. No spring-pop, no typewriter.
- Copy tone: authoritative, specific, understated. "Seit 1998 vertreten wir Mandanten" not "Wir sind Ihr Partner."
- Spacing: very generous. py-32 md:py-40 minimum on hero. Whitespace communicates premium.
"""


_BRIEF_SYSTEM_PROMPT = """You are a senior UI/UX designer writing design briefs for premium React websites.

HARD RULES — the brief must respect all of these:

COLOR:
- No AI-purple/blue gradient as primary accent (#6366f1, #7C3AED, #3B82F6, #8B5CF6 etc.) — most common AI fingerprint
- Exactly 1 accent color. Every CTA and highlight uses this exact accent, nothing else
- Accent saturation below 80% — desaturate so it blends, not screams
- No pure #000000 background — use off-blacks: #050505, #0a0a0a, #111111
- No beige+brass combination for "premium" — overused and reads as template
- NEVER navy + gold for lawyer/legal sites — this is the #1 most copied template look; even if the business is a law firm, pick something genuinely distinct
- Shadows tinted to match background hue — never pure rgba(0,0,0,0.3)
- ONE gray family only (warm OR cool) — never mix warm and cool grays in the same design
- Flat solid background is sterile — specify one of: subtle radial gradient, CSS noise overlay (opacity 0.02-0.04), or mesh gradient
- UNIQUENESS: Every design brief must produce a distinct visual identity. Two businesses in the same industry must NOT look like the same template with swapped text. If a suggested palette is provided, use it as the base — it was chosen specifically for this business.

FONTS:
- Banned: Inter, Roboto, Arial, Open Sans, Helvetica
- Sans options: Geist, Outfit, Cabinet Grotesk, Satoshi, Plus Jakarta Sans, Raleway, Syne, DM Sans
- Traditional professions (Anwalt, Notar, Arzt, Steuerberater, Architekt): consider a serif heading (Fraunces, Playfair Display, Cormorant Garamond) paired with a clean sans body

MOOD ADJECTIVES:
- Must be specific to this exact business — never generic AI defaults
- Banned: elegant, modern, professionell, innovativ, nahtlos, vertrauenswürdig, hochwertig
- Good examples: handwerklich + bodenständig + ehrlich / urban + präzise + direkt / warm + familiär + verlässlich

Output ONLY the requested brief fields. No preamble, no markdown headers, no explanation."""


def _build_design_brief_prompt(lead: dict, inspiration: str, ref_css: dict, structured: dict | None = None, design_analysis: dict | None = None, picked_animations: list | None = None, scraped_colors: list | None = None, suggested_palette: dict | None = None, ref_design_analyses: list | None = None, style_profile: dict | None = None) -> str:
    css_summary = ""
    if ref_css.get("computed"):
        parts = []
        for sel, vals in ref_css["computed"].items():
            if vals.get("font") and vals["font"] not in ("", "inherit"):
                parts.append(f"{sel}: font={vals['font']}, color={vals['color']}, bg={vals['bg']}")
        if parts:
            css_summary = "Extracted from reference site:\n" + "\n".join(parts[:5])

    services_preview = ""
    if structured:
        svcs = structured.get("services") or []
        if svcs:
            services_preview = "Key services: " + ", ".join(svcs[:4])

    about_preview = ""
    if structured:
        about = (structured.get("about") or "").strip()
        if about:
            about_preview = f"About: {about[:200]}"

    rating_info = ""
    if lead.get("google_rating"):
        rating_info = f"Google rating: {lead['google_rating']} ({lead.get('google_reviews', '')} reviews)"

    # Business-type hints
    category = lead.get("category", "")
    if category in {"Zahnarzt", "Kinderarzt"}:
        mode_hint = (
            f"Mode: LIGHT BACKGROUND MANDATORY for {category}. "
            f"Use white (#ffffff), off-white (#fdfaf5), or very light grey/mint (#f4f8f6). "
            f"NEVER dark backgrounds, NEVER navy, NEVER dark blue — patients associate dark dental sites with fear. "
            f"Accent must be soft teal, sage green, or warm grey — NEVER cold dark blue or AI-purple."
        )
    elif category in _LIGHT_MODE_CATEGORIES:
        mode_hint = f"Mode hint: {category} businesses read as clean and trustworthy — light background (white, off-white, or very light grey) is strongly preferred over dark OLED."
    elif category in _DARK_MODE_CATEGORIES:
        mode_hint = f"Mode hint: {category} businesses suit a dark, atmospheric background (zinc-950, #0a0a0a, deep navy). Dark mode preferred."
    else:
        mode_hint = "Mode: choose dark or light based on the business personality from the brief context — do not default to dark just because it looks premium."

    serif_hint = ""
    if category in _SERIF_CATEGORIES:
        serif_hint = f"Font note: {category} is a traditional profession — a serif heading font (Fraunces, Playfair Display, Cormorant Garamond) paired with a sans body is appropriate and differentiating."

    # Build current-site design analysis block for the brief
    analysis_block = ""
    if design_analysis:
        da = design_analysis
        fonts_found = da.get("fonts") or []
        banned_fonts = [f for f in fonts_found if any(b in f for b in ["Inter", "Roboto", "Arial", "Open Sans", "Helvetica"])]
        ok_fonts = [f for f in fonts_found if f not in banned_fonts]
        libs = da.get("animLibs") or []
        has_anim = da.get("hasScrollAnimations", False)
        has_transitions = da.get("hasTransitions", False)
        layout = da.get("layoutType", "unknown")

        font_note = ""
        if banned_fonts:
            font_note = f"Current site uses BANNED fonts ({', '.join(banned_fonts)}) — replace with premium alternatives."
        elif ok_fonts:
            font_note = f"Current site uses: {', '.join(ok_fonts)} — consider keeping or upgrading."
        else:
            font_note = "Current site fonts: not detected (likely system fonts)."

        anim_note = ""
        if not has_anim and not libs:
            anim_note = "Current site is STATIC — zero animations. Our redesign must be dramatically more dynamic and engaging."
        elif libs:
            anim_note = f"Current site uses: {', '.join(libs)}. Our redesign improves on this with motion/react + GSAP."
        else:
            anim_note = "Current site has basic scroll animations. Our redesign must be significantly more polished."

        transition_note = "No CSS transitions found — all interactive elements feel dead." if not has_transitions else "Some CSS transitions present."
        layout_note = f"Current layout: {layout}."

        analysis_block = (
            f"\n## Current Site Design Analysis (use as contrast — our redesign must be dramatically better)\n"
            f"- Fonts: {font_note}\n"
            f"- Animations: {anim_note}\n"
            f"- Interactions: {transition_note}\n"
            f"- Layout: {layout_note}\n"
        )

    # Reference site design pattern analysis block
    ref_analysis_block = ""
    if ref_design_analyses:
        ref_lines = []
        all_fonts = []
        all_libs = []
        layout_counts = {"grid-dominant": 0, "flex-dominant": 0}
        anim_sites = 0
        for da in ref_design_analyses:
            if not da:
                continue
            fonts = [f for f in (da.get("fonts") or []) if f not in ("", "inherit")]
            all_fonts.extend(fonts)
            all_libs.extend(da.get("animLibs") or [])
            lt = da.get("layoutType", "")
            if lt in layout_counts:
                layout_counts[lt] += 1
            if da.get("hasScrollAnimations"):
                anim_sites += 1

        unique_fonts = list(dict.fromkeys(all_fonts))[:5]
        unique_libs = list(dict.fromkeys(all_libs))
        dominant_layout = max(layout_counts, key=layout_counts.get) if any(layout_counts.values()) else "unknown"

        if unique_fonts:
            ref_lines.append(f"- Fonts in use: {', '.join(unique_fonts)} — consider these as the category standard, then differentiate")
        if unique_libs:
            ref_lines.append(f"- Animation libraries: {', '.join(unique_libs)} — category already expects motion")
        elif anim_sites == 0:
            ref_lines.append("- Animation: none detected — our demo will be dramatically more dynamic by comparison")
        else:
            ref_lines.append(f"- Scroll animations: {anim_sites}/{len(ref_design_analyses)} reference sites have them")
        ref_lines.append(f"- Layout pattern: {dominant_layout} — match or surpass this structural approach")

        if ref_lines:
            ref_analysis_block = (
                f"\n## CATEGORY BENCHMARK (real premium {category} sites — meet or exceed this bar)\n"
                + "\n".join(ref_lines) + "\n"
            )

    # Randomly select archetypes to force visual variance between generations
    vibe = random.choice(_VIBE_ARCHETYPES)
    layout = random.choice(_LAYOUT_ARCHETYPES)
    hero = random.choice(_HERO_PARADIGMS)
    motion = random.choice(_MOTION_LEVELS)

    # Color context blocks
    palette_block = ""
    if suggested_palette:
        p = suggested_palette
        palette_block = (
            f"\n## STARTING PALETTE — use these exact values as your base\n"
            f"bg: {p['bg']} | surface: {p['surface']} | text: {p['text']} | accent: {p['accent']} | shadow: {p['shadow']}\n"
            f"You MAY shift the accent ±10% in saturation/lightness if the business brand strongly justifies it. "
            f"Do NOT replace the background family (stay dark-on-dark or light-on-light). "
            f"Do NOT invent a purple, blue, or pink accent for this category.\n"
        )

    brand_colors_block = ""
    if scraped_colors:
        # Filter out transparent / very common values
        filtered = [c for c in scraped_colors if c not in ("rgba(0, 0, 0, 0)", "transparent", "rgb(0, 0, 0)", "rgb(255, 255, 255)")][:6]
        if filtered:
            brand_colors_block = (
                f"\n## EXISTING BRAND COLORS (scraped from current website)\n"
                f"{', '.join(filtered)}\n"
                f"If any of these are distinctive (non-generic), carry them into the redesign for brand continuity. "
                f"Generic system colors (white, black) can be ignored.\n"
            )

    # Formal-category premium rules
    formal_block = ""
    if category in _FORMAL_CATEGORIES:
        formal_block = _FORMAL_PREMIUM_RULES

    # Style profile — visual richness and image direction per category
    profile = style_profile or _DEFAULT_STYLE_PROFILE
    richness_map = {
        "editorial":   "Restrained and precise — every element earns its place. Max 4 animations. Long pauses between sections. Whitespace is the design.",
        "balanced":    "Professional but engaging — quality animations, clear hierarchy. 4-5 sections animated. Not boring, not showy.",
        "showcase":    "Portfolio-first — the work IS the hero. Large images dominate. Gallery section is the most important section. 5 animations minimum.",
        "expressive":  "Full creative expression — atmospheric, immersive, rich. 6 animations. Bold imagery. Every section should feel alive.",
    }
    richness_note = richness_map.get(profile["richness"], richness_map["balanced"])

    # Category-specific mandatory overrides — injected verbatim into the brief
    _CATEGORY_MANDATORY: dict[str, str] = {
        "Immobilienmakler": (
            "\n## IMMOBILIEN — PFLICHTANFORDERUNGEN (non-negotiable)\n"
            "This is a PROPERTY BUSINESS. Buyers/renters come to see homes — images ARE the product.\n"
            "MANDATORY in the generated website:\n"
            "1. EVERY section contains at least one large property image (interior or exterior)\n"
            "2. Angebote/Listings section: interactive image gallery or card carousel — each property card has a photo, price, size (m²), rooms\n"
            "3. Hero: full-bleed property photo background (interior or exterior), text overlay\n"
            "4. Use Picsum seeds that suggest real estate: 'apartment', 'interior', 'livingroom', 'realestate', 'architecture', 'exterior'\n"
            "5. Visual ratio: 60% image, 40% text across all sections\n"
            "6. NO generic office/business stock photos\n"
        ),
    }
    category_mandatory = _CATEGORY_MANDATORY.get(category, "")

    profile_block = (
        f"\n## CATEGORY VISUAL PROFILE ({category})\n"
        f"- Visual richness: {profile['richness'].upper()} — {richness_note}\n"
        f"- Image direction: {profile['image_mood']}\n"
        f"- Section emphasis: {profile['section_emphasis']}\n"
        f"- Animation count assigned: {profile['k']} techniques (see ANIMATION ASSIGNMENTS below)\n"
    )

    # Use pre-selected animation assignments (generated once in generate_demo for reuse in codegen)
    section_labels = [
        "Hero section",
        "Services / Leistungen section",
        "Über uns / About section",
        "Bewertungen / Stats section",
        "FAQ or secondary content section",
        "Kontakt / CTA section",
    ]
    picked_techniques = picked_animations or _pick_animations(lead.get("category", ""), k=6)
    animation_assignments = "\n".join(
        f"  - {label}: [{t['name']}] {t['desc']}"
        for label, t in zip(section_labels, picked_techniques)
    )

    color_field = (
        "- Color palette: background hex, text hex, accent hex (1 only), surface hex, shadow tint hex\n"
        "  Use the STARTING PALETTE above as base. Justify any accent deviation in 5 words.\n"
        if suggested_palette else
        "- Color palette: background hex, text hex, accent hex (1 only), surface hex, shadow tint hex\n"
        "  Justify accent in 5 words — why this color for THIS specific business\n"
    )

    return (
        f"Create a concise, BUSINESS-SPECIFIC design brief for:\n\n"
        f"Business: {lead.get('name', '')} ({category}) in {lead.get('district', 'Berlin')}\n"
        f"{services_preview}\n{about_preview}\n{rating_info}\n\n"
        f"{mode_hint}\n"
        f"{serif_hint}\n"
        f"{formal_block}"
        f"{category_mandatory}"
        f"{profile_block}"
        f"{palette_block}"
        f"{brand_colors_block}"
        f"{analysis_block}\n"
        f"{ref_analysis_block}"
        f"Category inspiration (do NOT copy directly — use as mood reference only):\n{inspiration}\n\n"
        f"{css_summary}\n\n"
        f"FORCED DESIGN DIRECTION for this generation (implement ALL of these exactly):\n"
        f"- Vibe archetype: {vibe}\n"
        f"- Layout archetype: {layout}\n"
        f"- Hero paradigm: {hero}\n"
        f"- Motion intensity: {motion}/10\n\n"
        f"ANIMATION ASSIGNMENTS — implement each technique in its assigned section. "
        f"These are unique to this generation and must not be swapped:\n"
        f"{animation_assignments}\n\n"
        f"Write a brief with EXACTLY these fields (concrete values only, no vague words):\n"
        f"{color_field}"
        f"- Background texture: radial-gradient / noise-overlay / mesh-gradient / clean-flat + one sentence why\n"
        f"- Gray family: warm or cool\n"
        f"- Font pairing: heading font (Google Fonts name), body font (Google Fonts name)\n"
        f"- Hero layout: implement the hero paradigm — specific composition description\n"
        f"- Visual mood: exactly 3 adjectives SPECIFIC to this business\n"
        f"- Confirm animation assignments: list each section + technique in one word\n"
        f"- Section details: for each of the 6 required sections, one sentence on the specific layout (e.g. 'Leistungen: alternating zigzag rows, image left on odd items; Bewertungen: horizontal scrolling marquee of 5-star cards')\n\n"
        f"Max 400 words. These values go directly into React/CSS code — be precise and specific to this business."
    )


def _post_process_jsx(jsx: str, design_brief: str = "") -> tuple[str, list[str]]:
    """
    Deterministic quality pass on generated App.jsx.
    Returns (fixed_jsx, list_of_warnings).
    Applies regex fixes for banned patterns; warns on brief non-compliance.
    """
    warnings = []
    original_len = len(jsx)

    # --- Regex auto-fixes (no LLM, deterministic) ---

    # 1. Em-dash and en-dash → hyphen
    em_count = jsx.count("—") + jsx.count("–")
    if em_count:
        jsx = jsx.replace("—", "-").replace("–", "-")
        warnings.append(f"AUTO-FIXED: {em_count} em/en-dashes replaced with hyphens")

    # 2. height: 100vh → minHeight: '100dvh' (JSX style objects)
    vh_jsx = len(re.findall(r"height:\s*['\"]100vh['\"]", jsx))
    if vh_jsx:
        jsx = re.sub(r"height:\s*'100vh'", "minHeight: '100dvh'", jsx)
        jsx = re.sub(r'height:\s*"100vh"', 'minHeight: "100dvh"', jsx)
        warnings.append(f"AUTO-FIXED: {vh_jsx} height:100vh → minHeight:100dvh (iOS Safari fix)")

    # 3. h-screen Tailwind class → min-h-[100dvh]
    hscreen_count = jsx.count("h-screen")
    if hscreen_count:
        jsx = jsx.replace("h-screen", "min-h-[100dvh]")
        warnings.append(f"AUTO-FIXED: {hscreen_count} h-screen → min-h-[100dvh]")

    # 4. ease-in-out in inline styles / transition strings (not in comments)
    ease_count = len(re.findall(r"ease-in-out(?!['\"]?\s*,?\s*//)", jsx))
    if ease_count:
        jsx = re.sub(r"ease-in-out", "cubic-bezier(0.16, 1, 0.3, 1)", jsx)
        warnings.append(f"AUTO-FIXED: {ease_count} ease-in-out → custom cubic-bezier")

    # 5. source.unsplash.com (shut down) → picsum.photos
    unsplash_count = jsx.count("source.unsplash.com")
    if unsplash_count:
        jsx = re.sub(
            r'https://source\.unsplash\.com/(\d+x\d+)/\?([^"\'>\s]+)',
            lambda m: f"https://picsum.photos/seed/{m.group(2).split(',')[0].replace('&', '-')}/{m.group(1).replace('x', '/')}",
            jsx,
        )
        warnings.append(f"AUTO-FIXED: {unsplash_count} dead Unsplash URLs → Picsum")

    # 6. Trailing decimal numbers (e.g. `0.` `1.` without digit after) → add trailing zero
    #    These cause esbuild "Expected '>' but found '.'" in JSX numeric expressions.
    trailing_dec = re.findall(r'\b(\d+\.(?!\d))', jsx)
    if trailing_dec:
        jsx = re.sub(r'\b(\d+\.)(?!\d)', lambda m: m.group(1) + '0', jsx)
        warnings.append(f"AUTO-FIXED: {len(trailing_dec)} trailing decimals (0. → 0.0) that would break esbuild")

    # 7. framer-motion → motion/react (template ships `motion` package, not `framer-motion`)
    fm_count = jsx.count("from 'framer-motion'") + jsx.count('from "framer-motion"')
    if fm_count:
        jsx = jsx.replace("from 'framer-motion'", "from 'motion/react'")
        jsx = jsx.replace('from "framer-motion"', 'from "motion/react"')
        warnings.append(f"AUTO-FIXED: {fm_count} framer-motion → motion/react import")

    # 9. Template placeholder comments inside JSX that break the build:
    #    {/* image or content block */} etc. left verbatim from code snippets
    placeholder_count = len(re.findall(r'\{/\*\s*(?:image|content block|item content|card|heading|scrolling content)[^*]*\*/\}', jsx, re.IGNORECASE))
    if placeholder_count:
        jsx = re.sub(r'\{/\*\s*(?:image|content block|item content|card|heading|scrolling content)[^*]*\*/\}', '{null}', jsx, flags=re.IGNORECASE)
        warnings.append(f"AUTO-FIXED: {placeholder_count} empty placeholder comments replaced with {{null}}")

    # --- Build-safety fixes: deterministic, don't alter rendered output ---

    # 10. Strip imports from packages not installed in the react-template
    _ALLOWED_PKGS = {'react', 'react-dom', 'react-dom/client', 'react-router-dom',
                     'gsap', 'motion', '@phosphor-icons/react'}
    def _pkg_allowed(pkg: str) -> bool:
        return pkg in _ALLOWED_PKGS or pkg.startswith(('gsap/', 'motion/', '@phosphor-icons/'))

    found_pkgs = set(re.findall(r"""from\s+['"]([^'"]+)['"]""", jsx))
    bad_pkgs = [p for p in found_pkgs if not _pkg_allowed(p)]
    if bad_pkgs:
        for pkg in bad_pkgs:
            jsx = re.sub(
                rf"""^import\s+[^\n]*from\s+['\"{re.escape(pkg)}['\"][^\n]*\n?""",
                '', jsx, flags=re.MULTILINE
            )
        warnings.append(f"AUTO-FIXED: stripped {len(bad_pkgs)} uninstalled import(s): {', '.join(sorted(bad_pkgs)[:4])}")

    # 11. Convert top-level require() → ESM import; dynamic require() → undefined
    def _req_to_import(m: re.Match) -> str:
        return f"import {m.group(1).strip()} from '{m.group(2)}'"
    req_top = len(re.findall(r'^(?:const|let|var)\s+\S+\s*=\s*require\(', jsx, re.MULTILINE))
    if req_top:
        jsx = re.sub(
            r'^(?:const|let|var)\s+(\{[^}]+\}|\w+)\s*=\s*require\([\'"]([^\'"]+)[\'"]\)\s*;?',
            _req_to_import, jsx, flags=re.MULTILINE
        )
        warnings.append(f"AUTO-FIXED: {req_top} top-level require() → ESM import")
    req_dyn = len(re.findall(r"""require\(['"][^'"]+['"]\)""", jsx))
    if req_dyn:
        jsx = re.sub(r"""require\(['"][^'"]+['"]\)""", 'undefined', jsx)
        warnings.append(f"AUTO-FIXED: {req_dyn} dynamic require() → undefined")

    # 12. Strip TypeScript interface/type declarations (break esbuild in .jsx files)
    ts_iface = len(re.findall(r'^\s*(?:export\s+)?interface\s+\w+', jsx, re.MULTILINE))
    ts_type  = len(re.findall(r'^\s*(?:export\s+)?type\s+\w+\s*=', jsx, re.MULTILINE))
    if ts_iface + ts_type:
        jsx = re.sub(r'\binterface\s+\w+[^{]*\{[^{}]*\}', '', jsx, flags=re.DOTALL)
        jsx = re.sub(r'\btype\s+\w+\s*=[^\n;]+;?', '', jsx)
        warnings.append(f"AUTO-FIXED: {ts_iface + ts_type} TypeScript interface/type declaration(s) removed")

    # 13. Strip React.FC<> type annotations from arrow functions
    ts_fc = len(re.findall(r':\s*React\.(?:FC|ReactNode|CSSProperties)(?:<[^>]*>)?(?=\s*=)', jsx))
    if ts_fc:
        jsx = re.sub(r':\s*React\.(?:FC|ReactNode|CSSProperties)(?:<[^>]*>)?(?=\s*=)', '', jsx)
        warnings.append(f"AUTO-FIXED: {ts_fc} React.FC type annotation(s) stripped")

    # 14. Strip stray CSS imports (only index.css ships in the demo bundle)
    css_imports = len(re.findall(r"""^import\s+['"][^'"]*\.css['"]\s*;?\n?""", jsx, re.MULTILINE))
    if css_imports:
        jsx = re.sub(r"""^import\s+['"][^'"]*\.css['"]\s*;?\n?""", '', jsx, flags=re.MULTILINE)
        warnings.append(f"AUTO-FIXED: {css_imports} stray CSS import(s) removed")

    # --- Design brief compliance checks (warnings only) ---
    if design_brief:
        # Extract hex colors from brief
        brief_hexes = re.findall(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', design_brief)
        if brief_hexes:
            missing = [h for h in brief_hexes[:5] if f"#{h}" not in jsx and h.lower() not in jsx.lower()]
            if len(missing) > len(brief_hexes) // 2:
                warnings.append(f"BRIEF COMPLIANCE: {len(missing)}/{len(brief_hexes)} brief hex colors not found in code ({', '.join('#'+h for h in missing[:3])})")

        # Check if brief font appears in code
        brief_fonts = re.findall(r"(?:heading font|body font|font pairing)[^\n]*?([A-Z][a-zA-Z\s]+(?:Grotesk|Display|Sans|Serif|Mono)?)", design_brief)
        for font in brief_fonts[:2]:
            font_clean = font.strip()
            if font_clean and font_clean not in jsx and font_clean.replace(" ", "+") not in jsx:
                warnings.append(f"BRIEF COMPLIANCE: Font '{font_clean}' from brief not found in code")

    # --- Animation variety check ---
    initial_patterns = re.findall(r'initial=\{\{([^}]+)\}\}', jsx)
    unique_initials = set(p.strip() for p in initial_patterns)
    if len(initial_patterns) > 3 and len(unique_initials) < 2:
        warnings.append(f"ANIMATION VARIETY: All {len(initial_patterns)} scroll animations use the same initial state — lacks variety")

    if warnings:
        print(f"[post-process] {len(warnings)} issues found/fixed in App.jsx ({original_len} → {len(jsx)} chars):")
        for w in warnings:
            print(f"  {'✓' if 'AUTO-FIXED' in w else '⚠'} {w}")

    return jsx, warnings


def _build_animation_checklist(picked_animations: list) -> str:
    """Build the mandatory animation implementation checklist for the codegen prompt."""
    section_labels = [
        "Hero section",
        "Services / Leistungen",
        "Über uns / About",
        "Bewertungen / Stats",
        "FAQ or secondary section",
        "Kontakt / CTA",
    ]
    lines = ["## ANIMATION IMPLEMENTATION CHECKLIST — ALL 6 ARE MANDATORY",
             "Implement each technique in its exact section. Do NOT substitute, skip, or reuse a technique.",
             "Do NOT default to generic whileInView={{opacity:0,y:32}} for any of these sections.\n"]
    for label, tech in zip(section_labels, picked_animations):
        lines.append(f"### {label} → [{tech['name']}]")
        lines.append(f"// {tech['desc']}")
        lines.append("```jsx")
        lines.append(tech["snippet"])
        lines.append("```\n")
    return "\n".join(lines)


def _extract_brief_mandatory(brief: str) -> str:
    """Extract critical values from design brief and inject as non-negotiable block at top of codegen prompt."""
    lines = [
        "## MANDATORY IMPLEMENTATION VALUES — DO NOT SUBSTITUTE",
        "These values were selected by the design brief. Use them exactly — no alternatives.\n",
    ]

    # Extract hex colors
    hexes = re.findall(r'#([0-9a-fA-F]{6})\b', brief)
    if hexes:
        unique = list(dict.fromkeys(h.upper() for h in hexes))[:6]
        color_list = ", ".join(f"#{h}" for h in unique)
        lines.append(f"- COLOR PALETTE (exact hex values only): {color_list}")
        lines.append(f"  → Use #{unique[0]} as background, #{unique[-1]} as accent on ALL CTAs and highlights.")
        lines.append("  → Do NOT invent new colors. Do NOT use generic blue/purple gradients.\n")

    # Extract font pairing — look for explicit font name mentions
    heading_m = re.search(
        r'(?:heading font|display font|headline font)[:\s]+([A-Z][A-Za-z\s]+?)(?:\s*[,\n(+]|$)',
        brief, re.IGNORECASE
    )
    body_m = re.search(
        r'(?:body font|body:[^,\n]*?|sans body)[:\s]+([A-Z][A-Za-z\s]+?)(?:\s*[,\n(]|$)',
        brief, re.IGNORECASE
    )
    # Fallback: look for "Font Pairing: X + Y"
    pairing_m = re.search(r'font pairing[:\s]+([A-Z][A-Za-z\s]+?)\s*\+\s*([A-Z][A-Za-z\s]+?)(?:\s*[,\n]|$)', brief, re.IGNORECASE)

    if pairing_m:
        hf = pairing_m.group(1).strip()
        bf = pairing_m.group(2).strip()
        lines.append(f"- FONTS: Heading = \"{hf}\" | Body = \"{bf}\"")
        lines.append(f"  → Import BOTH via @import in a <style> tag at top of the component. No Inter, no Roboto.\n")
    elif heading_m or body_m:
        if heading_m:
            lines.append(f"- HEADING FONT: \"{heading_m.group(1).strip()}\" — import via @import in <style> tag.")
        if body_m:
            lines.append(f"- BODY FONT: \"{body_m.group(1).strip()}\" — import via @import in <style> tag.")
        lines.append("")

    if len(lines) <= 2:
        return ""  # Nothing extracted, skip block

    lines.append("Violating any of the above = broken output.\n")
    return "\n".join(lines) + "\n"


def _build_codegen_prompt(
    lead: dict,
    content: dict,
    structured: dict,
    inspiration: str,
    design_brief: str,
    slug: str,
    n_ref_screenshots: int = 0,
    n_lead_screenshots: int = 0,
    picked_animations: list | None = None,
) -> str:
    # Services: prefer Haiku-extracted, fall back to heuristic
    services_list = structured.get("services") or content.get("services", [])
    services_text = "\n".join(f"- {s}" for s in services_list) or "Not specified"

    # Testimonials: prefer Haiku-extracted
    testimonials_list = structured.get("testimonials") or content.get("testimonials", [])
    testimonials_text = "\n".join(f'"{t}"' for t in testimonials_list) or "None found"

    # About text from Haiku extraction
    about_text = structured.get("about", "")

    # Contact: merge scraped regex + Haiku extraction
    phone = (structured.get("phone") or lead.get("phone") or content.get("contact", {}).get("phone", ""))
    email = (structured.get("email") or lead.get("email") or content.get("contact", {}).get("email", ""))
    opening_hours = structured.get("opening_hours", "")

    nav_text = ", ".join(content.get("nav_items", []))

    # Extract subpage URLs from subpage_text (format: "[url]:\ncontent")
    subpage_urls: list[str] = []
    for line in (content.get("subpage_text") or "").split("\n"):
        line = line.strip()
        if line.startswith("[http") and line.endswith("]:"):
            url = line[1:-2]
            subpage_urls.append(url)

    # Build route map: derive clean slug + label from URL path
    from urllib.parse import urlparse as _urlparse

    # Category-specific standard routes used as fallback when scraping finds no subpages
    _CATEGORY_ROUTES: dict[str, list[dict]] = {
        "Anwalt":            [{"path": "/rechtsgebiete", "label": "Rechtsgebiete"}, {"path": "/team", "label": "Team"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Rechtsanwalt":      [{"path": "/rechtsgebiete", "label": "Rechtsgebiete"}, {"path": "/team", "label": "Team"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Notar":             [{"path": "/leistungen", "label": "Leistungen"}, {"path": "/kanzlei", "label": "Kanzlei"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Steuerberater":     [{"path": "/leistungen", "label": "Leistungen"}, {"path": "/team", "label": "Team"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Architekt":         [{"path": "/projekte", "label": "Projekte"}, {"path": "/leistungen", "label": "Leistungen"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Arzt":              [{"path": "/leistungen", "label": "Leistungen"}, {"path": "/praxis", "label": "Praxis"}, {"path": "/team", "label": "Team"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Zahnarzt":          [{"path": "/leistungen", "label": "Leistungen"}, {"path": "/praxis", "label": "Praxis"}, {"path": "/team", "label": "Team"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Physiotherapeut":   [{"path": "/leistungen", "label": "Leistungen"}, {"path": "/praxis", "label": "Praxis"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Kosmetik":          [{"path": "/leistungen", "label": "Leistungen"}, {"path": "/preise", "label": "Preise"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Immobilienmakler":  [{"path": "/immobilien", "label": "Immobilien"}, {"path": "/leistungen", "label": "Leistungen"}, {"path": "/team", "label": "Team"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Restaurant":        [{"path": "/speisekarte", "label": "Speisekarte"}, {"path": "/reservierung", "label": "Reservierung"}, {"path": "/ueber-uns", "label": "Über uns"}],
        "Bar":               [{"path": "/karte", "label": "Karte"}, {"path": "/events", "label": "Events"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Fotograf":          [{"path": "/portfolio", "label": "Portfolio"}, {"path": "/leistungen", "label": "Leistungen"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Friseur":           [{"path": "/leistungen", "label": "Leistungen"}, {"path": "/preise", "label": "Preise"}, {"path": "/kontakt", "label": "Kontakt"}],
        "Barbier":           [{"path": "/leistungen", "label": "Leistungen"}, {"path": "/preise", "label": "Preise"}, {"path": "/kontakt", "label": "Kontakt"}],
    }
    _DEFAULT_ROUTES = [
        {"path": "/leistungen", "label": "Leistungen"},
        {"path": "/ueber-uns", "label": "Über uns"},
        {"path": "/kontakt", "label": "Kontakt"},
    ]

    routes: list[dict] = []
    seen_slugs: set = set()
    for url in subpage_urls[:8]:
        path = _urlparse(url).path.rstrip("/")
        if not path or path == "/":
            continue
        parts = [p for p in path.split("/") if p]
        route_slug = parts[-1].lower().replace("-", "-").replace("_", "-")[:30]
        if route_slug in seen_slugs:
            continue
        seen_slugs.add(route_slug)
        label = parts[-1].replace("-", " ").replace("_", " ").title()
        routes.append({"path": f"/{route_slug}", "label": label})

    # Always have routes — fall back to category standard if scraper found none
    if not routes:
        fallback = _CATEGORY_ROUTES.get(lead.get("category", ""), _DEFAULT_ROUTES)
        routes = [r for r in fallback if r["path"].lstrip("/") not in seen_slugs]

    route_lines = "\n".join(
        f'  - path="{r["path"]}" label="{r["label"]}"'
        + (f' (content from: {r["url"]})' if r.get("url") else " (generate content from business data)")
        for r in routes
    )
    routes_section = f"""
## Subpages — implement ALL as React Router routes (MANDATORY, not optional)
Route "/" is the main marketing landing page (hero, key sections, CTA).
These additional routes are REQUIRED — each is a dedicated full page component:
{route_lines}

NEVER build a single-page scroll app. Always use React Router with these routes.
The Nav must link to ALL routes using <NavLink> with active styling.
Each subpage must have its own full layout: hero/header, main content, CTA, footer.
Content for generated pages: derive from business name, category, and all scraped data.
"""

    # Parse red flags
    raw_flags = lead.get("red_flags", "[]")
    try:
        flags = json.loads(raw_flags) if isinstance(raw_flags, str) else (raw_flags or [])
    except Exception:
        flags = []

    # Build weakness section
    weakness_lines = []
    ps_mobile = lead.get("pagespeed_mobile")
    ps_desktop = lead.get("pagespeed_desktop")
    seo_score = lead.get("seo_score")
    if ps_mobile is not None:
        weakness_lines.append(f"- Mobile PageSpeed: {ps_mobile}/100{' — critically slow, optimize heavily' if ps_mobile < 50 else ''}")
    if ps_desktop is not None:
        weakness_lines.append(f"- Desktop PageSpeed: {ps_desktop}/100")
    if seo_score is not None:
        weakness_lines.append(f"- SEO Score: {seo_score}/100 — fix with proper structure, headings, meta tags")
    if not lead.get("has_cta"):
        weakness_lines.append("- No CTA found — add prominent booking/contact button above the fold")
    if not lead.get("has_booking"):
        weakness_lines.append("- No booking system — add a clear appointment/contact CTA")
    if not lead.get("is_mobile_ready"):
        weakness_lines.append("- Not mobile-optimized — demo must be fully responsive")
    for flag in flags:
        weakness_lines.append(f"- {flag}")
    weakness_section = (
        "## Known Issues — Fix ALL of These in the Demo\n" + "\n".join(weakness_lines)
        if weakness_lines else ""
    )

    # Images: real <img> tags + CSS background images
    scraped_images = content.get("images", [])
    bg_images = content.get("bg_images", [])
    if scraped_images or bg_images:
        img_lines = "\n".join(
            f'  src="{i.get("src", "")}" alt="{i.get("alt", "")}"'
            for i in scraped_images[:12]
            if i.get("src", "").startswith("http")
        )
        bg_lines = "\n".join(f'  background-image: url("{u}")' for u in bg_images[:8])
        image_section = (
            "## Real Images from Their Current Website\n"
            "Use these as <img src={...}> props where appropriate:\n"
            f"{img_lines}\n"
            + (f"\nCSS background images (use as hero/section backgrounds):\n{bg_lines}" if bg_lines else "")
        )
    else:
        image_section = "## Images\nNo real images found — use the Unsplash placeholder URLs provided below."

    # Screenshot context block — label each image by its index
    screenshot_lines = []
    idx = 1
    if n_ref_screenshots > 0:
        labels = ["hero/nav area", "services/features section", "lower section/footer"]
        for i in range(n_ref_screenshots):
            label = labels[i] if i < len(labels) else f"section {i+1}"
            screenshot_lines.append(
                f"Image {idx}: REFERENCE SITE ({label}) — "
                f"Extract: exact color palette, font weight hierarchy, section spacing rhythm, card/button styles, nav pattern. "
                f"Your output MUST reach or exceed this visual quality. If it wouldn't impress someone who saw this reference, redo it."
            )
            idx += 1
    if n_lead_screenshots > 0:
        lead_labels = ["hero/nav area", "mid section"]
        for i in range(n_lead_screenshots):
            label = lead_labels[i] if i < len(lead_labels) else f"section {i+1}"
            screenshot_lines.append(
                f"Image {idx}: CURRENT CLIENT SITE ({label}) — "
                f"This is what they have now. Preserve every real name, service, text, and contact detail. "
                f"The visual redesign must be dramatically better — same content, premium execution."
            )
            idx += 1

    if screenshot_lines:
        preamble = (
            "MANDATORY: Before writing a single line of JSX, visually analyze ALL attached screenshots.\n"
            "Reference sites = the quality bar for this category. Client site = content source.\n"
        )
        screenshot_context = preamble + "\n".join(screenshot_lines) + "\n\n"
    else:
        screenshot_context = ""

    schema_type = SCHEMA_TYPES.get(lead.get("category", ""), "LocalBusiness")

    # Category-specific Unsplash keywords for contextually relevant placeholder images
    _CATEGORY_KEYWORDS: dict[str, dict[str, str]] = {
        "Zahnarzt": {"hero": "dental,clinic,teeth", "service": "dentist,treatment", "about": "dental,professional,smile", "team": "doctor,medical,team"},
        "Arzt": {"hero": "medical,clinic,doctor", "service": "healthcare,medicine", "about": "doctor,professional", "team": "medical,team"},
        "Physiotherapeut": {"hero": "physiotherapy,treatment", "service": "massage,therapy,exercise", "about": "therapist,wellness", "team": "physiotherapy,professional"},
        "Restaurant": {"hero": "restaurant,dining,food", "service": "food,dish,meal", "about": "chef,kitchen,cuisine", "team": "restaurant,chef"},
        "Cafe": {"hero": "cafe,coffee,interior", "service": "coffee,pastry,drink", "about": "barista,cafe", "team": "cafe,barista"},
        "Friseur": {"hero": "hair,salon,hairdresser", "service": "haircut,styling,hair", "about": "hairdresser,salon", "team": "hairstylist,salon"},
        "Kosmetik": {"hero": "beauty,salon,skincare", "service": "cosmetic,beauty,treatment", "about": "beauty,professional", "team": "beauty,therapist"},
        "Fitnessstudio": {"hero": "gym,fitness,workout", "service": "exercise,training,weights", "about": "fitness,trainer", "team": "personal,trainer,fitness"},
        "Yoga": {"hero": "yoga,meditation,studio", "service": "yoga,pose,wellness", "about": "yoga,instructor", "team": "yoga,teacher"},
        "Anwalt": {"hero": "law,office,professional", "service": "lawyer,legal,court", "about": "attorney,professional", "team": "lawyer,team"},
        "Steuerberater": {"hero": "office,business,professional", "service": "finance,accounting,tax", "about": "accountant,professional", "team": "business,team"},
        "Immobilien": {"hero": "real-estate,building,architecture", "service": "apartment,house,property", "about": "realtor,professional", "team": "real-estate,team"},
        "Hotel": {"hero": "hotel,lobby,luxury", "service": "hotel,room,bedroom", "about": "hotel,hospitality", "team": "hotel,staff"},
        "Fotograf": {"hero": "photography,camera,studio", "service": "photography,portrait,wedding", "about": "photographer,professional", "team": "photographer"},
        "Handwerk": {"hero": "workshop,tools,craftsman", "service": "tools,construction,repair", "about": "craftsman,professional", "team": "craftsman,team"},
        "Reinigung": {"hero": "cleaning,professional,service", "service": "cleaning,hygiene,tidy", "about": "cleaning,professional", "team": "cleaning,team"},
        "Tierarzt": {"hero": "veterinary,animal,clinic", "service": "pet,veterinary,care", "about": "veterinarian,animal", "team": "vet,doctor"},
        "Apotheke": {"hero": "pharmacy,medicine,health", "service": "pharmacy,medicine,pills", "about": "pharmacist,health", "team": "pharmacist,team"},
        "Optiker": {"hero": "optician,glasses,eyewear", "service": "glasses,eyewear,lens", "about": "optician,professional", "team": "optician,team"},
        "Fahrschule": {"hero": "driving,car,school", "service": "car,driving,lesson", "about": "driving,instructor", "team": "instructor,team"},
    }
    cat = lead.get("category", "") or ""
    kw = _CATEGORY_KEYWORDS.get(cat, {"hero": f"{cat},business,professional", "service": f"{cat},service", "about": "office,professional,team", "team": "team,professional"})

    cat_slug = cat.lower().replace(" ", "-").replace("/", "-")
    picsum_block = (
        f"## Placeholder Images (use where no real images available)\n"
        f"Use Picsum with descriptive seeds — apply style={{{{ filter: 'grayscale(15%) contrast(1.08)' }}}} to every Picsum image:\n"
        f"Hero/Banner: https://picsum.photos/seed/{cat_slug}-hero/1600/900\n"
        f"Service 1: https://picsum.photos/seed/{cat_slug}-service-a/800/600\n"
        f"Service 2: https://picsum.photos/seed/{cat_slug}-service-b/800/600\n"
        f"Service 3: https://picsum.photos/seed/{cat_slug}-service-c/800/600\n"
        f"About/Team: https://picsum.photos/seed/{cat_slug}-team/1200/800\n"
        f"Never use source.unsplash.com — that endpoint is shut down.\n"
    )

    animation_checklist = _build_animation_checklist(picked_animations) if picked_animations else ""

    # Extract mandatory values from brief so they appear at top of prompt
    brief_mandatory = _extract_brief_mandatory(design_brief)

    # === Structured data blocks for injection into codegen prompt ===

    # Team members
    _team_list = structured.get("team") or []
    if _team_list:
        _team_lines = "\n".join(
            f"  - {m.get('name', '?')}, {m.get('title', '?')}"
            + (f" — {m['specialization']}" if m.get("specialization") else "")
            for m in _team_list
        )
        team_data_block = (
            f"Team (use REAL names — do NOT invent fake team members):\n{_team_lines}"
        )
    else:
        team_data_block = ""

    # Price list (beauty/wellness)
    _price_list = structured.get("price_list") or []
    if _price_list:
        _price_lines = "\n".join(
            f"  - {p.get('service', '?')}: {p.get('price', '?')}"
            + (f" ({p['duration']})" if p.get("duration") else "")
            for p in _price_list
        )
        price_data_block = (
            f"\n## Real Price List (use EXACTLY these — do NOT invent prices):\n{_price_lines}"
        )
    else:
        price_data_block = ""

    # Portfolio / projects (Architekt, Fotograf, Handwerker, etc.)
    _projects_list = structured.get("projects") or []
    if _projects_list:
        _proj_lines = "\n".join(
            f"  - {p.get('name', '?')}"
            + (f" ({p['type']})" if p.get("type") else "")
            + (f", {p['year']}" if p.get("year") else "")
            + (f", {p['location']}" if p.get("location") else "")
            + (f": {p['description']}" if p.get("description") else "")
            for p in _projects_list
        )
        projects_data_block = (
            f"\n## Real Projects / Portfolio ({len(_projects_list)} items — use these names, do NOT invent fake projects):\n{_proj_lines}"
        )
    else:
        projects_data_block = ""

    # Menu items (Restaurant, Cafe, Bar)
    _menu_items = structured.get("menu_items") or []
    if _menu_items:
        _menu_json = json.dumps(_menu_items, ensure_ascii=False, indent=2)
        menu_data_block = (
            f"\n## Real Menu Items ({len(_menu_items)} items scraped — use ALL in Speisekarte section):\n"
            f"```json\n{_menu_json}\n```"
        )
    else:
        menu_data_block = ""

    # Category-specific required section overrides (replaces generic 7-section list in system prompt)

    # ── Immobilienmakler: use real properties if scraped ─────────────────────
    _real_properties = structured.get("properties") or []
    if _real_properties:
        _props_json = json.dumps(_real_properties, ensure_ascii=False, indent=2)
        _angebote_instruction = (
            f"   Each card: large photo (16:9 aspect), price in €, size in m², room count, district/location badge. "
            f"Use the {len(_real_properties)} REAL properties below — display ALL of them. "
            f"Fill any null fields with realistic Berlin data. Interactive hover states on cards."
        )
        _real_props_block = (
            f"\n## REAL PROPERTY LISTINGS (scraped — use ALL {len(_real_properties)}, do NOT replace with mock data):\n"
            f"```json\n{_props_json}\n```\n"
        )
    else:
        _angebote_instruction = (
            "   Each card: large photo (16:9 aspect), price in €, size in m², room count, district/location badge. "
            "Min 4 mock properties with realistic Berlin prices (€380k–€1.2M Kauf, €1.200–€3.800/Monat Miete). "
            "Interactive hover states on cards."
        )
        _real_props_block = ""

    # ── Anwalt: team-aware, Rechtsgebiete-first ──────────────────────────────
    _anwalt_team = (
        f"\n   Real lawyers to feature (use exact names):\n{_team_lines}"
        if _team_list else
        "\n   Use realistic German lawyer names (Herr/Frau Dr./LL.M.) if no real team found."
    )

    # ── Architekt: inject real project names if scraped ──────────────────────
    _architekt_projects = (
        f"\n## Real Projects (use these exact names in the Projekte gallery):\n{_proj_lines}"
        if _projects_list else ""
    )

    # ── Restaurant: inject real menu if scraped ───────────────────────────────
    _restaurant_menu = menu_data_block if _menu_items else (
        "\n## Mock menu: invent 6-8 dishes that fit this restaurant's cuisine style, with realistic Berlin prices (€12–€28 Hauptgerichte)."
    )

    _CATEGORY_SECTION_OVERRIDES: dict[str, str] = {
        "Immobilienmakler": (
            "\n## ═══════════════════════════════════════════════════════\n"
            "## REQUIRED SECTIONS — IMMOBILIEN (overrides default list)\n"
            "## ═══════════════════════════════════════════════════════\n"
            "This is a property business. Images ARE the product. Every section must be image-dominant.\n\n"
            "1. Nav: floating pill — business name + phone (right) + CTA 'Kostenlose Bewertung'\n"
            "2. Hero: min-h-[100dvh] full-bleed property photo. Headline + 2 CTAs: 'Aktuelle Objekte' + 'Kostenlose Wertermittlung'\n"
            "3. Aktuelle Angebote — LARGEST SECTION: property listing cards in grid or masonry.\n"
            + _angebote_instruction + "\n"
            + "4. Leistungen: Verkauf / Vermietung / Immobilienbewertung — asymmetric layout, image per service\n"
            "5. Über uns / Team: agent photo, years experience, transaction count as animated stat\n"
            "6. Bewertungen: seller + buyer testimonials with star ratings\n"
            "7. Kontakt: phone + email + address + contact form. CTA: 'Jetzt kostenlose Immobilienbewertung anfragen'\n"
            "8. Footer\n\n"
            "PICSUM SEEDS: 'apartment', 'interior', 'livingroom', 'modernkitchen', 'architecture', 'realestate', 'facade'\n"
            + _real_props_block
        ),
        "Zahnarzt": (
            "\n## ═══════════════════════════════════════════════════════\n"
            "## REQUIRED SECTIONS — ZAHNARZT (overrides default list)\n"
            "## ═══════════════════════════════════════════════════════\n"
            "Clean, light, premium dental practice. Light background MANDATORY — white/off-white ONLY.\n\n"
            "1. Nav: floating pill — practice name + phone + CTA 'Termin vereinbaren'\n"
            "2. Hero: min-h-[100dvh], light background + large hero image (dental equipment or bright clinic — NOT a stock dentist). Calm headline + Google rating badge + CTA 'Termin online buchen'\n"
            "3. Leistungen: dental services as bento or zigzag — each with dental image. Min 4 services.\n"
            "4. Behandlungsablauf / Praxis: practice interior photos, modern equipment, welcoming atmosphere.\n"
            "5. Bewertungen: patient testimonials with star ratings (trust-critical for dental)\n"
            "6. Team / Über uns: doctor/team photo, credentials, years of experience\n"
            "7. Kontakt: address + phone + online booking CTA + opening hours\n"
            "8. Footer\n\n"
            "PICSUM SEEDS: 'dental', 'clinic', 'medical-equipment', 'white-interior', 'modern-clinic', 'healthcare'\n"
        ),
        "Anwalt": (
            "\n## ═══════════════════════════════════════════════════════\n"
            "## REQUIRED SECTIONS — ANWALT / KANZLEI (overrides default list)\n"
            "## ═══════════════════════════════════════════════════════\n"
            "This is a law firm. Authority, discretion, and expertise are the product.\n\n"
            "1. Nav: floating pill — firm name + phone + CTA 'Erstberatung anfragen' — dark editorial style\n"
            "2. Hero: min-h-[100dvh], editorial dark background (use palette). Large authoritative headline about the core practice area. Trust badge: years since founding + Kammer membership. Primary CTA 'Jetzt Erstberatung anfragen'\n"
            "3. Rechtsgebiete — LARGEST SECTION: each practice area as a distinct card with icon, heading, and 2-sentence scope description. Layout: asymmetric bento or editorial grid (NOT equal 3-col). Min 4 areas from the scraped services.\n"
            "4. Anwälte / Team: lawyer profiles with placeholder photo, real name (if found), title (Rechtsanwalt/Rechtsanwältin, LL.M., Dr.), and specialization." + _anwalt_team + "\n"
            "5. Mandatsablauf: 3–4 steps showing how a case engagement works (Erstgespräch → Analyse → Strategie → Vertretung). Clean timeline layout.\n"
            "6. Bewertungen / Mandate: client testimonials (if found) OR 2-3 anonymized case type descriptions ('Erfolgreich vertreten im Bereich...')\n"
            "7. Kontakt: office address + phone + email + contact form. Note: 'Alle Anfragen werden vertraulich behandelt.'\n"
            "8. Footer\n\n"
            "PICSUM SEEDS: 'law', 'office', 'books', 'architecture', 'marble', 'desk'\n"
            "TONE: authoritative, understated, specific — 'Seit 2003 vertreten wir Mandanten', never 'Wir sind Ihr Partner'\n"
        ),
        "Rechtsanwalt": (
            "\n## ═══════════════════════════════════════════════════════\n"
            "## REQUIRED SECTIONS — RECHTSANWALT (overrides default list)\n"
            "## ═══════════════════════════════════════════════════════\n"
            "Solo law practice. Personal authority and focused expertise.\n\n"
            "1. Nav: floating pill — lawyer name + phone + CTA 'Erstberatung'\n"
            "2. Hero: editorial dark or warm-parchment background. Name + title prominent. Core specialization headline. CTA 'Erstberatung anfragen'\n"
            "3. Rechtsgebiete — DOMINANT: each practice area as editorial card. Min 3 areas.\n"
            "4. Über mich: personal profile — background, approach, philosophy. NOT generic. 1 photo placeholder.\n"
            "5. Mandatsablauf: 3-step process (Kontakt → Analyse → Vertretung)\n"
            "6. Bewertungen: client testimonials if found, else strong credentials block\n"
            "7. Kontakt: address + phone + email + form\n"
            "8. Footer\n\n"
            "PICSUM SEEDS: 'law', 'office', 'books', 'architecture'\n"
        ),
        "Architekt": (
            "\n## ═══════════════════════════════════════════════════════\n"
            "## REQUIRED SECTIONS — ARCHITEKT (overrides default list)\n"
            "## ═══════════════════════════════════════════════════════\n"
            "This is an architecture practice. The work IS the product — portfolio dominates everything.\n\n"
            "1. Nav: ultra-minimal floating bar — practice name only (left) + 'Projekt anfragen' (right). No clutter.\n"
            "2. Hero: full-bleed architectural project photo (dramatic angle, natural light). Minimal text: practice name + one-line philosophy. No crowded CTAs.\n"
            "3. Projekte / Portfolio — THE DOMINANT SECTION (largest, most prominent): masonry grid or large-format image gallery showing multiple projects. Each entry: project photo, name, type (Neubau/Umbau/Innenarchitektur), year, location. Min 4 projects." + _architekt_projects + "\n"
            "4. Leistungen: Neubau / Umbau / Innenarchitektur / Städtebau — editorial list, image per service\n"
            "5. Büro / Über uns: founding story, design philosophy, team. Clean editorial layout.\n"
            "6. Auszeichnungen / Referenzen: awards, publications, client names if certifications found\n"
            "7. Kontakt: minimal — email + phone + studio address. Clean form.\n"
            "8. Footer\n\n"
            "PICSUM SEEDS: 'architecture', 'building', 'interior', 'modern-house', 'facade', 'concrete'\n"
            "DESIGN RULE: Whitespace IS the design. No decorative elements. Typography and photography carry everything.\n"
        ),
        "Steuerberater": (
            "\n## ═══════════════════════════════════════════════════════\n"
            "## REQUIRED SECTIONS — STEUERBERATER (overrides default list)\n"
            "## ═══════════════════════════════════════════════════════\n"
            "Modern tax advisory firm. Approachable expertise — boutique feel, not Big 4 stiffness.\n\n"
            "1. Nav: floating pill — firm name + phone + CTA 'Erstgespräch vereinbaren'\n"
            "2. Hero: clean editorial background (use palette). Headline about the firm's specialization or target client. Trust signals: Steuerberaterkammer membership + years of experience. CTA 'Kostenloses Erstgespräch'\n"
            "3. Leistungen — clear and comprehensive: Steuerberatung / Buchhaltung / Jahresabschluss / Lohnbuchhaltung / Unternehmensberatung / Erbschaftsteuer. Layout: clean icon-card grid (NOT boring equal columns — use bento or editorial grouping). Source from scraped services.\n"
            "4. Für wen — client segments (helps visitors self-qualify): Selbstständige & Freiberufler / GmbH & Kapitalgesellschaften / Privatpersonen / Immobilienbesitzer / Existenzgründer. Short 2-sentence value prop per segment.\n"
            "5. Berater / Team: advisor profiles — real names if found, credentials (Steuerberater, Diplom-Kaufmann, LL.M.), specializations." + (f"\n   Real team:\n{_team_lines}" if _team_list else "") + "\n"
            "6. Prozess: onboarding steps — Erstgespräch → Analyse → Mandat → laufende Betreuung. Clean numbered timeline.\n"
            "7. Kontakt: address + phone + email + contact form. Mention: 'Diskretion und Vertraulichkeit selbstverständlich.'\n"
            "8. Footer\n\n"
            "PICSUM SEEDS: 'office', 'desk', 'finance', 'business', 'documents'\n"
            "TONE: competent and warm — 'Wir kennen Ihre Situation', not 'Optimieren Sie Ihre Steuerlast'\n"
        ),
        "Restaurant": (
            "\n## ═══════════════════════════════════════════════════════\n"
            "## REQUIRED SECTIONS — RESTAURANT (overrides default list)\n"
            "## ═══════════════════════════════════════════════════════\n"
            "Atmosphere and food are the product. Reservations are the conversion goal.\n\n"
            "1. Nav: restaurant name (with logo area) + 'Jetzt reservieren' CTA (accent color)\n"
            "2. Hero: full-bleed food/atmosphere photography. Restaurant name + tagline. 'Jetzt reservieren' + 'Speisekarte' CTAs.\n"
            "3. Speisekarte Highlights — KEY SECTION: organized menu with category headers (Vorspeisen, Hauptgerichte, Desserts, Getränke). Large food photography per category." + _restaurant_menu + "\n"
            "4. Atmosphäre: interior photos grid, ambiance description, capacity/seating info, any private dining\n"
            "5. Über uns / Geschichte: restaurant story, head chef name, cuisine concept and inspiration\n"
            "6. Reservierung: prominent booking section — phone number large, online form or 'Tisch reservieren' CTA\n"
            "7. Kontakt + Öffnungszeiten: address, opening hours (formatted clearly), Google Maps link\n"
            "8. Footer\n\n"
            "PICSUM SEEDS: 'food', 'restaurant', 'dining', 'dish', 'kitchen', 'chef', 'interior'\n"
            "DESIGN RULE: Every section must have large food or atmosphere photography. Text-heavy sections are death for restaurants.\n"
        ),
        "Cafe": (
            "\n## ═══════════════════════════════════════════════════════\n"
            "## REQUIRED SECTIONS — CAFÉ (overrides default list)\n"
            "## ═══════════════════════════════════════════════════════\n"
            "Cozy, inviting, neighborhood feel. Goal: people want to come in.\n\n"
            "1. Nav: cafe name + 'Speisekarte' + address or hours hint\n"
            "2. Hero: full-bleed warm cafe interior or latte art photography. Inviting headline.\n"
            "3. Speisekarte: coffee menu + food menu. Grid with photos." + _restaurant_menu + "\n"
            "4. Atmosphäre: interior photos, cozy details, seating areas\n"
            "5. Über uns: cafe story, who runs it, why they love coffee\n"
            "6. Öffnungszeiten + Standort: hours table + address + map link\n"
            "7. Footer\n"
        ),
    }
    category_section_override = _CATEGORY_SECTION_OVERRIDES.get(lead.get("category", ""), "")

    return f"""
Generate a complete single-file React App.jsx for this German business demo website.

## ═══════════════════════════════════════════════════════
## CREATIVE OVERRIDE — THIS IS YOUR PRIMARY DIRECTIVE
## ═══════════════════════════════════════════════════════

You are operating in maximum creative output mode. This is not a template fill-in job.
Every layout decision must be deliberate, specific to this business, and visually surprising in a good way.

LAYOUT: Before coding, mentally sketch 3 different hero layouts. Pick the most unexpected one that still converts.
Asymmetric grids, editorial splits, full-bleed photography with text overlay, large typographic heroes —
choose based on the business personality, NOT on what's easiest to code.

BRAND VOICE: Read the existing website copy carefully. Extract: Is it formal or informal? Long sentences or short?
Does it use "Sie" (formal) or "du" (casual)? Is the tone warm, authoritative, minimalist, or energetic?
Then write ALL generated German copy in that exact voice and vocabulary level.
Never default to generic business-speak ("Wir bieten Ihnen...") — match what they actually sound like.

DISTINCTIVENESS CHALLENGE: After generating each section, ask yourself: "Could this section appear on any other
{lead.get('category', 'business')} website?" If yes — redesign it. Every section must be unmistakably THIS business.

## ═══════════════════════════════════════════════════════
## DESIGN DIRECTIVES — READ THESE FIRST, IMPLEMENT EXACTLY
## ═══════════════════════════════════════════════════════

{animation_checklist}

{brief_mandatory}

## Design Brief — ALL VALUES ARE MANDATORY, NOT SUGGESTIONS
{design_brief}

## Category Design Inspiration (mood reference — match this energy)
{inspiration}

## ═══════════════════════════════════════════════════════
## REFERENCE SCREENSHOTS — STUDY THESE BEFORE CODING
## ═══════════════════════════════════════════════════════
{screenshot_context}
{routes_section}

## ═══════════════════════════════════════════════════════
## BUSINESS DATA — USE VERBATIM, DO NOT INVENT
## ═══════════════════════════════════════════════════════

## Business Info
Name: {lead.get('name', '')}
Category: {lead.get('category', '')}
District: {lead.get('district', 'Berlin')}
Address: {lead.get('address', '')}
Phone: {phone}
Email: {email}
{f"Opening hours: {opening_hours}" if opening_hours else ""}
Website: {lead.get('website', '')}
Google Rating: {lead.get('google_rating', '')} ({lead.get('google_reviews', '')} Bewertungen)
{f"Founded: {structured.get('founding_year')}" if structured.get('founding_year') else ""}
{("Certifications / Memberships: " + " | ".join(structured.get('certifications', []))) if structured.get('certifications') else ""}
{team_data_block}

## About This Business
{about_text or content.get('description', '') or 'No about text found.'}

## Existing Website Content — COPY THIS TEXT VERBATIM
CRITICAL RULE: Every heading, service name, team member, location, testimonial, and body text must come DIRECTLY from the source below. Do NOT invent, paraphrase, or swap in generic text. If a name, city, or service appears in the source — use it exactly. Only invent content where the source has absolutely no equivalent.

Current title: {content.get('title', '')}
Current tagline: {content.get('tagline', '')}
Navigation: {nav_text}
Services:
{services_text}
Testimonials:
{testimonials_text}
Main page text:
{content.get('raw_text', '')[:12000]}

{f"Subpages (USE ALL NAMES, LOCATIONS, SERVICES MENTIONED):{chr(10)}{content.get('subpage_text', '')[:12000]}" if content.get('subpage_text') else ""}

{image_section}

{picsum_block}
{price_data_block}
{projects_data_block}
{menu_data_block}

{weakness_section}

## SEO & AEO Requirements (implement ALL — non-negotiable)

### Meta Tags (set via useEffect on mount)
- document.title: "{lead.get('name', '')} — {lead.get('category', '')} in {lead.get('district', 'Berlin')}"
- meta[name="description"]: 150-160 Zeichen, enthält Hauptleistung + Standort + USP
- meta[property="og:title"], meta[property="og:description"], meta[property="og:locale"] content="de_DE"
- meta[name="robots"] content="index, follow"

### Schema.org JSON-LD (render as <script type="application/ld+json"> in JSX via dangerouslySetInnerHTML)
Primary type: {schema_type}
Required fields: name, address (streetAddress, addressLocality, addressCountry="DE"), telephone, url
If google_rating exists: include aggregateRating (ratingValue + reviewCount)
FAQPage schema: wrap all FAQ question/answer pairs as Question + Answer entities

### Semantic HTML Structure
- Exactly ONE <h1>: business name or primary tagline
- Section titles as <h2>: Leistungen, Über uns, Prozess, Bewertungen, FAQ, Kontakt
- Individual service/feature names as <h3>
- Body text in <p>, lists in <ul>/<li>
- Use semantic elements: <header>, <main>, <section>, <footer>, <nav>, <address>

### AEO Content Structure (for AI search engines)
- FAQ: each question as clear <h3>, answer as 2-3 sentence <p> — direct and factual
- "Über uns": structured paragraph covering who / what / where / since when
- Contact section: NAP (Name, Adresse, Telefon) consistent with business info
- No filler text — every sentence must be scannable and informative

{category_section_override}

## Output Rules
- Output ONLY valid JSX starting with import statements
- No markdown fences, no explanation text
- React is auto-imported by Vite — do NOT write a bare `import React from 'react'`
  If you need hooks, use ONLY: import {{ useState, useEffect, useRef, useCallback }} from 'react' (once, combined)
  Never write both `import React from 'react'` AND `import {{ useState }} from 'react'` — that causes a build error
- All components defined in one file, exported as: export default function App()
- Google Fonts: import via a <style> tag rendered in the component, e.g.:
  const FontImport = () => (
    <style>{{`@import url('https://fonts.googleapis.com/css2?family=...');`}}</style>
  )
- Tailwind v4: use utility classes directly, no config needed
- motion/react: import {{ motion, useScroll, useTransform, useInView, useReducedMotion }} from 'motion/react'
- gsap: import {{ gsap }} from 'gsap'; import {{ ScrollTrigger }} from 'gsap/ScrollTrigger'
- Icons: import from '@phosphor-icons/react'. Use ONLY real icon names — the build WILL FAIL for any invalid name.
  IMPORTANT naming rules (these common mistakes break the build):
  - NO ChevronDown/ChevronUp/ChevronRight/ChevronLeft (don't exist) → use CaretDown/CaretUp/CaretRight/CaretLeft
  - NO Activity, Fork, Tags (don't exist) → use Heartbeat, ForkKnife, Tag instead
  Common valid icons: Phone, PhoneCall, MapPin, NavigationArrow, Star, StarHalf, StarFour,
  ArrowRight, ArrowLeft, ArrowUp, ArrowDown, ArrowCircleRight, ArrowClockwise,
  CheckCircle, Check, CheckSquare, CheckFat, Clock, Timer, HourglassMedium,
  Heart, HeartStraight, Heartbeat, House, HouseLine, User, Users, UserCircle, UserPlus,
  Camera, Image, Images, Calendar, CalendarBlank, CalendarCheck,
  Envelope, EnvelopeSimple, Globe, GlobeSimple, GlobeHemisphereWest,
  MagnifyingGlass, Warning, WarningCircle, Info, Question,
  ShieldCheck, ShieldStar, Trophy, Medal, Leaf, Plant,
  Tag, TagSimple, Pencil, PencilSimple, Trash, TrashSimple,
  Link, LinkSimple, Share, ShareNetwork, BookOpen, Book, Article,
  ChartBar, ChartLine, ChartPie, TrendUp, TrendDown,
  CreditCard, Wallet, Money, ShoppingCart, ShoppingBag, Storefront, Receipt,
  Stethoscope, FirstAid, Bandaids, Pill, Pulse,
  Wrench, Hammer, Scissors, Ruler, Toolbox, Package,
  Coffee, ForkKnife, Pizza, Wine, Cake,
  GraduationCap, Student, Barbell, MusicNote, MusicNotes,
  Car, Bicycle, Truck, Airplane,
  CaretDown, CaretUp, CaretRight, CaretLeft, CaretDoubleRight, CaretDoubleLeft,
  X, XCircle, Plus, PlusCircle, Minus, MinusCircle, DotsThree, DotsThreeVertical,
  List, ListBullets, ListChecks, Eye, EyeSlash, Lock, LockOpen, Key,
  Bell, BellSimple, Chat, ChatCircle, Megaphone, Broadcast,
  SpinnerGap, CircleNotch, Sun, Moon, Cloud, Wind, Thermometer,
  Lightning, Sparkle, Fire, Drop, Snowflake,
  InstagramLogo, FacebookLogo, TwitterLogo, LinkedinLogo, YoutubeLogo, WhatsappLogo,
  Rocket, Robot, Brain, Lightbulb, Target, Strategy, Gauge, Funnel
  Example: import {{ Phone, MapPin, Star, CheckCircle, ArrowRight }} from '@phosphor-icons/react'
- React Router: import {{ BrowserRouter, Routes, Route, Link, NavLink, useLocation }} from 'react-router-dom'
- All copy in German

## Routing Architecture
- App() renders: <BrowserRouter><Layout /></BrowserRouter>
- Layout component: sticky Nav + <Outlet /> + Footer (uses useOutlet or nested Routes)
- Route "/" = HomePage: full marketing landing page (hero, key sections, CTAs)
- Additional routes for each subpage listed above — each is its own page component
- Nav uses <NavLink> with active styling (e.g. className={{{{ isActive }}}} => isActive ? 'underline' : '')
- useLocation() for scroll-to-top on route change (useEffect on location.pathname)
- ALWAYS use React Router — never build a single-page scroll app

## Home Page Structure
- Required: sticky Nav (always first) + Hero + Footer (always last)
- Everything between Hero and Footer: YOU decide what sections fit this specific business
  A law firm: Rechtsgebiete, Team/Anwälte, Referenzen, Kontakt
  A restaurant: Speisekarte highlights, Atmosphäre, Reservierung, Kontakt
  Adapt to the actual business — do NOT default to the same generic order every time

- Each section must be fully implemented — no placeholders, no TODOs, no "// add more here" comments
## ANIMATION PHILOSOPHY
Use motion/react and GSAP where it serves the design — not everywhere by default.
Before adding any animation, ask: what does this communicate? (hierarchy, storytelling, feedback, state change)
Minimum: at least 4 meaningful animations chosen based on what fits THIS specific design.
Available tools: motion/react whileInView stagger, GSAP ScrollTrigger (sticky stack, parallax, horizontal pan), spring physics on interactive elements, clip-path reveals, blur-fade transitions.
Every CTA button must have whileTap={{ scale: 0.97 }}. Beyond that: your judgment.

## DESIGN UNIQUENESS RULE
This website must look VISUALLY DISTINCT from any other website in the same category.
- Do NOT use the generic 3-column equal feature cards layout
- Do NOT use the AI-purple gradient default
- Implement the specific vibe and layout archetype from the Design Brief above
- Every section must use a different layout family (no same layout repeated)

- Nav must have a working mobile hamburger menu with animated open/close (lines morph to X)
- Hero must have a clear primary CTA button
- Kontakt section must show phone, email, address, and a styled contact form
- COMPLETENESS IS MANDATORY: generate the full implementation, minimum 900 lines of JSX
- Do NOT truncate, abbreviate, or simplify any section to save tokens — a complete site is required

## TRUST ARCHITECTURE — mandatory for every output
This website is a sales tool. A prospect who has never heard of this business must trust them enough to call or book within 30 seconds of landing. Implement ALL of these:

- Google Rating: display prominently within the first scroll — star rating + number of reviews as a visible badge (e.g. in hero or immediately below). Never hide it. If rating >= 4.5, make it a hero element.
- Years in business: if founding_year is provided, show "Seit [year]" or "Über X Jahre Erfahrung" in the hero or directly below it — not buried in the About section.
- Certifications/Memberships: if any certifications are listed above, display them as trust badges with icons — ShieldCheck, Medal, Trophy, or Certificate icon from Phosphor. Never skip them.
- Phone number: must appear in the Nav (top right), in the Hero section, AND in the footer. Three times minimum.
- Address: must appear in the Kontakt section and the footer with a visual map pin icon.
- Testimonials: if any exist, they must be styled as proper review cards with star rating, reviewer name, and quote — not a plain blockquote. Minimum 3 testimonials displayed.
- Primary CTA: "Termin vereinbaren" or "Jetzt anfragen" must appear above the fold, AND after the Leistungen section, AND in the final Kontakt section.

## TRUST PRE-FLIGHT (silent check before outputting)
Answer mentally before generating:
1. Can a stranger immediately see what this business does? (hero headline)
2. Can they immediately see where the business is? (district + address visible above fold)
3. Can they see proof others trust this business? (rating/reviews/testimonials visible without scrolling)
4. Can they contact the business in one click from anywhere on the page? (phone in nav)
5. Are all certifications and memberships displayed as visible trust signals?
If any answer is NO — fix it before outputting.
""".strip()


def _dedup_react_imports(app_jsx: str) -> str:
    """Merge duplicate React imports — prevents 'React already declared' build error."""
    lines = app_jsx.split("\n")
    react_imports: list[str] = []
    other_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^import\s+React", stripped) or re.match(r'^import\s*\{[^}]*\}\s*from\s*["\']react["\']', stripped):
            react_imports.append(stripped)
        else:
            other_lines.append(line)
    if len(react_imports) <= 1:
        return app_jsx

    # Merge: collect all named imports + decide if default React is needed
    named: set[str] = set()
    needs_default = False
    for imp in react_imports:
        # `import React from 'react'`
        if re.match(r"^import React from", imp):
            needs_default = True
        # `import React, { useState } from 'react'`
        m = re.match(r"^import React,\s*\{([^}]+)\}", imp)
        if m:
            needs_default = True
            for n in m.group(1).split(","):
                named.add(n.strip())
        # `import { useState, useEffect } from 'react'`
        m = re.match(r"^import\s*\{([^}]+)\}\s*from\s*['\"]react['\"]", imp)
        if m:
            for n in m.group(1).split(","):
                named.add(n.strip())

    if needs_default and named:
        merged = f"import React, {{ {', '.join(sorted(named))} }} from 'react'"
    elif needs_default:
        merged = "import React from 'react'"
    elif named:
        merged = f"import {{ {', '.join(sorted(named))} }} from 'react'"
    else:
        merged = "import React from 'react'"

    print(f"[demo] Merged {len(react_imports)} React imports → {merged}")
    return "\n".join([merged] + other_lines)


_VALID_PHOSPHOR_ICONS: frozenset[str] = frozenset({
    "Acorn", "AddressBook", "AddressBookTabs", "AirTrafficControl", "Airplane", "AirplaneInFlight", "AirplaneLanding", "AirplaneTakeoff", "AirplaneTaxiing", "AirplaneTilt",
    "Airplay", "Alarm", "Alien", "AlignBottom", "AlignBottomSimple", "AlignCenterHorizontal", "AlignCenterHorizontalSimple", "AlignCenterVertical", "AlignCenterVerticalSimple", "AlignLeft",
    "AlignLeftSimple", "AlignRight", "AlignRightSimple", "AlignTop", "AlignTopSimple", "AmazonLogo", "Ambulance", "Anchor", "AnchorSimple", "AndroidLogo",
    "Angle", "AngularLogo", "Aperture", "AppStoreLogo", "AppWindow", "AppleLogo", "ApplePodcastsLogo", "ApproximateEquals", "Archive", "Armchair",
    "ArrowArcLeft", "ArrowArcRight", "ArrowBendDoubleUpLeft", "ArrowBendDoubleUpRight", "ArrowBendDownLeft", "ArrowBendDownRight", "ArrowBendLeftDown", "ArrowBendLeftUp", "ArrowBendRightDown", "ArrowBendRightUp",
    "ArrowBendUpLeft", "ArrowBendUpRight", "ArrowCircleDown", "ArrowCircleDownLeft", "ArrowCircleDownRight", "ArrowCircleLeft", "ArrowCircleRight", "ArrowCircleUp", "ArrowCircleUpLeft", "ArrowCircleUpRight",
    "ArrowClockwise", "ArrowCounterClockwise", "ArrowDown", "ArrowDownLeft", "ArrowDownRight", "ArrowElbowDownLeft", "ArrowElbowDownRight", "ArrowElbowLeft", "ArrowElbowLeftDown", "ArrowElbowLeftUp",
    "ArrowElbowRight", "ArrowElbowRightDown", "ArrowElbowRightUp", "ArrowElbowUpLeft", "ArrowElbowUpRight", "ArrowFatDown", "ArrowFatLeft", "ArrowFatLineDown", "ArrowFatLineLeft", "ArrowFatLineRight",
    "ArrowFatLineUp", "ArrowFatLinesDown", "ArrowFatLinesLeft", "ArrowFatLinesRight", "ArrowFatLinesUp", "ArrowFatRight", "ArrowFatUp", "ArrowLeft", "ArrowLineDown", "ArrowLineDownLeft",
    "ArrowLineDownRight", "ArrowLineLeft", "ArrowLineRight", "ArrowLineUp", "ArrowLineUpLeft", "ArrowLineUpRight", "ArrowRight", "ArrowSquareDown", "ArrowSquareDownLeft", "ArrowSquareDownRight",
    "ArrowSquareIn", "ArrowSquareLeft", "ArrowSquareOut", "ArrowSquareRight", "ArrowSquareUp", "ArrowSquareUpLeft", "ArrowSquareUpRight", "ArrowUDownLeft", "ArrowUDownRight", "ArrowULeftDown",
    "ArrowULeftUp", "ArrowURightDown", "ArrowURightUp", "ArrowUUpLeft", "ArrowUUpRight", "ArrowUp", "ArrowUpLeft", "ArrowUpRight", "ArrowsClockwise", "ArrowsCounterClockwise",
    "ArrowsDownUp", "ArrowsHorizontal", "ArrowsIn", "ArrowsInCardinal", "ArrowsInLineHorizontal", "ArrowsInLineVertical", "ArrowsInSimple", "ArrowsLeftRight", "ArrowsMerge", "ArrowsOut",
    "ArrowsOutCardinal", "ArrowsOutLineHorizontal", "ArrowsOutLineVertical", "ArrowsOutSimple", "ArrowsSplit", "ArrowsVertical", "Article", "ArticleMedium", "ArticleNyTimes", "Asclepius",
    "Asterisk", "AsteriskSimple", "At", "Atom", "Avocado", "Axe", "Baby", "BabyCarriage", "Backpack", "Backspace",
    "Bag", "BagSimple", "Balloon", "Bandaids", "Bank", "Barbell", "Barcode", "Barn", "Barricade", "Baseball",
    "BaseballCap", "BaseballHelmet", "Basket", "Basketball", "Bathtub", "BatteryCharging", "BatteryChargingVertical", "BatteryEmpty", "BatteryFull", "BatteryHigh",
    "BatteryLow", "BatteryMedium", "BatteryPlus", "BatteryPlusVertical", "BatteryVerticalEmpty", "BatteryVerticalFull", "BatteryVerticalHigh", "BatteryVerticalLow", "BatteryVerticalMedium", "BatteryWarning",
    "BatteryWarningVertical", "BeachBall", "Beanie", "Bed", "BeerBottle", "BeerStein", "BehanceLogo", "Bell", "BellRinging", "BellSimple",
    "BellSimpleRinging", "BellSimpleSlash", "BellSimpleZ", "BellSlash", "BellZ", "Belt", "BezierCurve", "Bicycle", "Binary", "Binoculars",
    "Biohazard", "Bird", "Blueprint", "Bluetooth", "BluetoothConnected", "BluetoothSlash", "BluetoothX", "Boat", "Bomb", "Bone",
    "Book", "BookBookmark", "BookOpen", "BookOpenText", "BookOpenUser", "Bookmark", "BookmarkSimple", "Bookmarks", "BookmarksSimple", "Books",
    "Boot", "Boules", "BoundingBox", "BowlFood", "BowlSteam", "BowlingBall", "BoxArrowDown", "BoxArrowUp", "BoxingGlove", "BracketsAngle",
    "BracketsCurly", "BracketsRound", "BracketsSquare", "Brain", "Brandy", "Bread", "Bridge", "Briefcase", "BriefcaseMetal", "Broadcast",
    "Broom", "Browser", "Browsers", "Bug", "BugBeetle", "BugDroid", "Building", "BuildingApartment", "BuildingOffice", "Buildings",
    "Bulldozer", "Bus", "Butterfly", "CableCar", "Cactus", "Cake", "Calculator", "Calendar", "CalendarBlank", "CalendarCheck",
    "CalendarDot", "CalendarDots", "CalendarHeart", "CalendarMinus", "CalendarPlus", "CalendarSlash", "CalendarStar", "CalendarX", "CallBell", "Camera",
    "CameraPlus", "CameraRotate", "CameraSlash", "Campfire", "Car", "CarBattery", "CarProfile", "CarSimple", "Cardholder", "Cards",
    "CardsThree", "CaretCircleDoubleDown", "CaretCircleDoubleLeft", "CaretCircleDoubleRight", "CaretCircleDoubleUp", "CaretCircleDown", "CaretCircleLeft", "CaretCircleRight", "CaretCircleUp", "CaretCircleUpDown",
    "CaretDoubleDown", "CaretDoubleLeft", "CaretDoubleRight", "CaretDoubleUp", "CaretDown", "CaretLeft", "CaretLineDown", "CaretLineLeft", "CaretLineRight", "CaretLineUp",
    "CaretRight", "CaretUp", "CaretUpDown", "Carrot", "CashRegister", "CassetteTape", "CastleTurret", "Cat", "CellSignalFull", "CellSignalHigh",
    "CellSignalLow", "CellSignalMedium", "CellSignalNone", "CellSignalSlash", "CellSignalX", "CellTower", "Certificate", "Chair", "Chalkboard", "ChalkboardSimple",
    "ChalkboardTeacher", "Champagne", "ChargingStation", "ChartBar", "ChartBarHorizontal", "ChartDonut", "ChartLine", "ChartLineDown", "ChartLineUp", "ChartPie",
    "ChartPieSlice", "ChartPolar", "ChartScatter", "Chat", "ChatCentered", "ChatCenteredDots", "ChatCenteredSlash", "ChatCenteredText", "ChatCircle", "ChatCircleDots",
    "ChatCircleSlash", "ChatCircleText", "ChatDots", "ChatSlash", "ChatTeardrop", "ChatTeardropDots", "ChatTeardropSlash", "ChatTeardropText", "ChatText", "Chats",
    "ChatsCircle", "ChatsTeardrop", "Check", "CheckCircle", "CheckFat", "CheckSquare", "CheckSquareOffset", "Checkerboard", "Checks", "Cheers",
    "Cheese", "ChefHat", "Cherries", "Church", "Cigarette", "CigaretteSlash", "Circle", "CircleDashed", "CircleHalf", "CircleHalfTilt",
    "CircleNotch", "CirclesFour", "CirclesThree", "CirclesThreePlus", "Circuitry", "City", "Clipboard", "ClipboardText", "Clock", "ClockAfternoon",
    "ClockClockwise", "ClockCountdown", "ClockCounterClockwise", "ClockUser", "ClosedCaptioning", "Cloud", "CloudArrowDown", "CloudArrowUp", "CloudCheck", "CloudFog",
    "CloudLightning", "CloudMoon", "CloudRain", "CloudSlash", "CloudSnow", "CloudSun", "CloudWarning", "CloudX", "Clover", "Club",
    "CoatHanger", "CodaLogo", "Code", "CodeBlock", "CodeSimple", "CodepenLogo", "CodesandboxLogo", "Coffee", "CoffeeBean", "Coin",
    "CoinVertical", "Coins", "Columns", "ColumnsPlusLeft", "ColumnsPlusRight", "Command", "Compass", "CompassRose", "CompassTool", "ComputerTower",
    "Confetti", "ContactlessPayment", "Control", "Cookie", "CookingPot", "Copy", "CopySimple", "Copyleft", "Copyright", "CornersIn",
    "CornersOut", "Couch", "CourtBasketball", "Cow", "CowboyHat", "Cpu", "Crane", "CraneTower", "CreditCard", "Cricket",
    "Crop", "Cross", "Crosshair", "CrosshairSimple", "Crown", "CrownCross", "CrownSimple", "Cube", "CubeFocus", "CubeTransparent",
    "CurrencyBtc", "CurrencyCircleDollar", "CurrencyCny", "CurrencyDollar", "CurrencyDollarSimple", "CurrencyEth", "CurrencyEur", "CurrencyGbp", "CurrencyInr", "CurrencyJpy",
    "CurrencyKrw", "CurrencyKzt", "CurrencyNgn", "CurrencyRub", "Cursor", "CursorClick", "CursorText", "Cylinder", "Database", "Desk",
    "Desktop", "DesktopTower", "Detective", "DevToLogo", "DeviceMobile", "DeviceMobileCamera", "DeviceMobileSlash", "DeviceMobileSpeaker", "DeviceRotate", "DeviceTablet",
    "DeviceTabletCamera", "DeviceTabletSpeaker", "Devices", "Diamond", "DiamondsFour", "DiceFive", "DiceFour", "DiceOne", "DiceSix", "DiceThree",
    "DiceTwo", "Disc", "DiscoBall", "DiscordLogo", "Divide", "Dna", "Dog", "Door", "DoorOpen", "Dot",
    "DotOutline", "DotsNine", "DotsSix", "DotsSixVertical", "DotsThree", "DotsThreeCircle", "DotsThreeCircleVertical", "DotsThreeOutline", "DotsThreeOutlineVertical", "DotsThreeVertical",
    "Download", "DownloadSimple", "Dress", "Dresser", "DribbbleLogo", "Drone", "Drop", "DropHalf", "DropHalfBottom", "DropSimple",
    "DropSlash", "DropboxLogo", "Ear", "EarSlash", "Egg", "EggCrack", "Eject", "EjectSimple", "Elevator", "Empty",
    "Engine", "Envelope", "EnvelopeOpen", "EnvelopeSimple", "EnvelopeSimpleOpen", "Equalizer", "Equals", "Eraser", "EscalatorDown", "EscalatorUp",
    "Exam", "ExclamationMark", "Exclude", "ExcludeSquare", "Export", "Eye", "EyeClosed", "EyeSlash", "Eyedropper", "EyedropperSample",
    "Eyeglasses", "Eyes", "FaceMask", "FacebookLogo", "Factory", "Faders", "FadersHorizontal", "FalloutShelter", "Fan", "Farm",
    "FastForward", "FastForwardCircle", "Feather", "FediverseLogo", "FigmaLogo", "File", "FileArchive", "FileArrowDown", "FileArrowUp", "FileAudio",
    "FileC", "FileCSharp", "FileCloud", "FileCode", "FileCpp", "FileCss", "FileCsv", "FileDashed", "FileDoc", "FileHtml",
    "FileImage", "FileIni", "FileJpg", "FileJs", "FileJsx", "FileLock", "FileMagnifyingGlass", "FileMd", "FileMinus", "FilePdf",
    "FilePlus", "FilePng", "FilePpt", "FilePy", "FileRs", "FileSql", "FileSvg", "FileText", "FileTs", "FileTsx",
    "FileTxt", "FileVideo", "FileVue", "FileX", "FileXls", "FileZip", "Files", "FilmReel", "FilmScript", "FilmSlate",
    "FilmStrip", "Fingerprint", "FingerprintSimple", "FinnTheHuman", "Fire", "FireExtinguisher", "FireSimple", "FireTruck", "FirstAid", "FirstAidKit",
    "Fish", "FishSimple", "Flag", "FlagBanner", "FlagBannerFold", "FlagCheckered", "FlagPennant", "Flame", "Flashlight", "Flask",
    "FlipHorizontal", "FlipVertical", "FloppyDisk", "FloppyDiskBack", "FlowArrow", "Flower", "FlowerLotus", "FlowerTulip", "FlyingSaucer", "Folder",
    "FolderDashed", "FolderLock", "FolderMinus", "FolderOpen", "FolderPlus", "FolderSimple", "FolderSimpleDashed", "FolderSimpleLock", "FolderSimpleMinus", "FolderSimplePlus",
    "FolderSimpleStar", "FolderSimpleUser", "FolderStar", "FolderUser", "Folders", "Football", "FootballHelmet", "Footprints", "ForkKnife", "FourK",
    "FrameCorners", "FramerLogo", "Function", "Funnel", "FunnelSimple", "FunnelSimpleX", "FunnelX", "GameController", "Garage", "GasCan",
    "GasPump", "Gauge", "Gavel", "Gear", "GearFine", "GearSix", "GenderFemale", "GenderIntersex", "GenderMale", "GenderNeuter",
    "GenderNonbinary", "GenderTransgender", "Ghost", "Gif", "Gift", "GitBranch", "GitCommit", "GitDiff", "GitFork", "GitMerge",
    "GitPullRequest", "GithubLogo", "GitlabLogo", "GitlabLogoSimple", "Globe", "GlobeHemisphereEast", "GlobeHemisphereWest", "GlobeSimple", "GlobeSimpleX", "GlobeStand",
    "GlobeX", "Goggles", "Golf", "GoodreadsLogo", "GoogleCardboardLogo", "GoogleChromeLogo", "GoogleDriveLogo", "GoogleLogo", "GooglePhotosLogo", "GooglePlayLogo",
    "GooglePodcastsLogo", "Gps", "GpsFix", "GpsSlash", "Gradient", "GraduationCap", "Grains", "GrainsSlash", "Graph", "GraphicsCard",
    "GreaterThan", "GreaterThanOrEqual", "GridFour", "GridNine", "Guitar", "HairDryer", "Hamburger", "Hammer", "Hand", "HandArrowDown",
    "HandArrowUp", "HandCoins", "HandDeposit", "HandEye", "HandFist", "HandGrabbing", "HandHeart", "HandPalm", "HandPeace", "HandPointing",
    "HandSoap", "HandSwipeLeft", "HandSwipeRight", "HandTap", "HandWaving", "HandWithdraw", "Handbag", "HandbagSimple", "HandsClapping", "HandsPraying",
    "Handshake", "HardDrive", "HardDrives", "HardHat", "Hash", "HashStraight", "HeadCircuit", "Headlights", "Headphones", "Headset",
    "Heart", "HeartBreak", "HeartHalf", "HeartStraight", "HeartStraightBreak", "Heartbeat", "Hexagon", "HighDefinition", "HighHeel", "Highlighter",
    "HighlighterCircle", "Hockey", "Hoodie", "Horse", "Hospital", "Hourglass", "HourglassHigh", "HourglassLow", "HourglassMedium", "HourglassSimple",
    "HourglassSimpleHigh", "HourglassSimpleLow", "HourglassSimpleMedium", "House", "HouseLine", "HouseSimple", "Hurricane", "IceCream", "IdentificationBadge", "IdentificationCard",
    "Image", "ImageBroken", "ImageSquare", "Images", "ImagesSquare", "Infinity", "Info", "InstagramLogo", "Intersect", "IntersectSquare",
    "IntersectThree", "Intersection", "Invoice", "Island", "Jar", "JarLabel", "Jeep", "Joystick", "Kanban", "Key",
    "KeyReturn", "Keyboard", "Keyhole", "Knife", "Ladder", "LadderSimple", "Lamp", "LampPendant", "Laptop", "Lasso",
    "LastfmLogo", "Layout", "Leaf", "Lectern", "Lego", "LegoSmiley", "LessThan", "LessThanOrEqual", "LetterCircleH", "LetterCircleP",
    "LetterCircleV", "Lifebuoy", "Lightbulb", "LightbulbFilament", "Lighthouse", "Lightning", "LightningA", "LightningSlash", "LineSegment", "LineSegments",
    "LineVertical", "Link", "LinkBreak", "LinkSimple", "LinkSimpleBreak", "LinkSimpleHorizontal", "LinkSimpleHorizontalBreak", "LinkedinLogo", "LinktreeLogo", "LinuxLogo",
    "List", "ListBullets", "ListChecks", "ListDashes", "ListHeart", "ListMagnifyingGlass", "ListNumbers", "ListPlus", "ListStar", "Lock",
    "LockKey", "LockKeyOpen", "LockLaminated", "LockLaminatedOpen", "LockOpen", "LockSimple", "LockSimpleOpen", "Lockers", "Log", "MagicWand",
    "Magnet", "MagnetStraight", "MagnifyingGlass", "MagnifyingGlassMinus", "MagnifyingGlassPlus", "Mailbox", "MapPin", "MapPinArea", "MapPinLine", "MapPinPlus",
    "MapPinSimple", "MapPinSimpleArea", "MapPinSimpleLine", "MapTrifold", "MarkdownLogo", "MarkerCircle", "Martini", "MaskHappy", "MaskSad", "MastodonLogo",
    "MathOperations", "MatrixLogo", "Medal", "MedalMilitary", "MediumLogo", "Megaphone", "MegaphoneSimple", "MemberOf", "Memory", "MessengerLogo",
    "MetaLogo", "Meteor", "Metronome", "Microphone", "MicrophoneSlash", "MicrophoneStage", "Microscope", "MicrosoftExcelLogo", "MicrosoftOutlookLogo", "MicrosoftPowerpointLogo",
    "MicrosoftTeamsLogo", "MicrosoftWordLogo", "Minus", "MinusCircle", "MinusSquare", "Money", "MoneyWavy", "Monitor", "MonitorArrowUp", "MonitorPlay",
    "Moon", "MoonStars", "Moped", "MopedFront", "Mosque", "Motorcycle", "Mountains", "Mouse", "MouseLeftClick", "MouseMiddleClick",
    "MouseRightClick", "MouseScroll", "MouseSimple", "MusicNote", "MusicNoteSimple", "MusicNotes", "MusicNotesMinus", "MusicNotesPlus", "MusicNotesSimple", "NavigationArrow",
    "Needle", "Network", "NetworkSlash", "NetworkX", "Newspaper", "NewspaperClipping", "NotEquals", "NotMemberOf", "NotSubsetOf", "NotSupersetOf",
    "Notches", "Note", "NoteBlank", "NotePencil", "Notebook", "Notepad", "Notification", "NotionLogo", "NuclearPlant", "NumberCircleEight",
    "NumberCircleFive", "NumberCircleFour", "NumberCircleNine", "NumberCircleOne", "NumberCircleSeven", "NumberCircleSix", "NumberCircleThree", "NumberCircleTwo", "NumberCircleZero", "NumberEight",
    "NumberFive", "NumberFour", "NumberNine", "NumberOne", "NumberSeven", "NumberSix", "NumberSquareEight", "NumberSquareFive", "NumberSquareFour", "NumberSquareNine",
    "NumberSquareOne", "NumberSquareSeven", "NumberSquareSix", "NumberSquareThree", "NumberSquareTwo", "NumberSquareZero", "NumberThree", "NumberTwo", "NumberZero", "Numpad",
    "Nut", "NyTimesLogo", "Octagon", "OfficeChair", "Onigiri", "OpenAiLogo", "Option", "Orange", "OrangeSlice", "Oven",
    "Package", "PaintBrush", "PaintBrushBroad", "PaintBrushHousehold", "PaintBucket", "PaintRoller", "Palette", "Panorama", "Pants", "PaperPlane",
    "PaperPlaneRight", "PaperPlaneTilt", "Paperclip", "PaperclipHorizontal", "Parachute", "Paragraph", "Parallelogram", "Park", "Password", "Path",
    "PatreonLogo", "Pause", "PauseCircle", "PawPrint", "PaypalLogo", "Peace", "Pen", "PenNib", "PenNibStraight", "Pencil",
    "PencilCircle", "PencilLine", "PencilRuler", "PencilSimple", "PencilSimpleLine", "PencilSimpleSlash", "PencilSlash", "Pentagon", "Pentagram", "Pepper",
    "Percent", "Person", "PersonArmsSpread", "PersonSimple", "PersonSimpleBike", "PersonSimpleCircle", "PersonSimpleHike", "PersonSimpleRun", "PersonSimpleSki", "PersonSimpleSnowboard",
    "PersonSimpleSwim", "PersonSimpleTaiChi", "PersonSimpleThrow", "PersonSimpleWalk", "Perspective", "Phone", "PhoneCall", "PhoneDisconnect", "PhoneIncoming", "PhoneList",
    "PhoneOutgoing", "PhonePause", "PhonePlus", "PhoneSlash", "PhoneTransfer", "PhoneX", "PhosphorLogo", "Pi", "PianoKeys", "PicnicTable",
    "PictureInPicture", "PiggyBank", "Pill", "PingPong", "PintGlass", "PinterestLogo", "Pinwheel", "Pipe", "PipeWrench", "PixLogo",
    "Pizza", "Placeholder", "Planet", "Plant", "Play", "PlayCircle", "PlayPause", "Playlist", "Plug", "PlugCharging",
    "Plugs", "PlugsConnected", "Plus", "PlusCircle", "PlusMinus", "PlusSquare", "PokerChip", "PoliceCar", "Polygon", "Popcorn",
    "Popsicle", "PottedPlant", "Power", "Prescription", "Presentation", "PresentationChart", "Printer", "Prohibit", "ProhibitInset", "ProjectorScreen",
    "ProjectorScreenChart", "Pulse", "PushPin", "PushPinSimple", "PushPinSimpleSlash", "PushPinSlash", "PuzzlePiece", "QrCode", "Question", "QuestionMark",
    "Queue", "Quotes", "Rabbit", "Racquet", "Radical", "Radio", "RadioButton", "Radioactive", "Rainbow", "RainbowCloud",
    "Ranking", "ReadCvLogo", "Receipt", "ReceiptX", "Record", "Rectangle", "RectangleDashed", "Recycle", "RedditLogo", "Repeat",
    "RepeatOnce", "ReplitLogo", "Resize", "Rewind", "RewindCircle", "RoadHorizon", "Robot", "Rocket", "RocketLaunch", "Rows",
    "RowsPlusBottom", "RowsPlusTop", "Rss", "RssSimple", "Rug", "Ruler", "Sailboat", "Scales", "Scan", "ScanSmiley",
    "Scissors", "Scooter", "Screencast", "Screwdriver", "Scribble", "ScribbleLoop", "Scroll", "Seal", "SealCheck", "SealPercent",
    "SealQuestion", "SealWarning", "Seat", "Seatbelt", "SecurityCamera", "Selection", "SelectionAll", "SelectionBackground", "SelectionForeground", "SelectionInverse",
    "SelectionPlus", "SelectionSlash", "Shapes", "Share", "ShareFat", "ShareNetwork", "Shield", "ShieldCheck", "ShieldCheckered", "ShieldChevron",
    "ShieldPlus", "ShieldSlash", "ShieldStar", "ShieldWarning", "ShippingContainer", "ShirtFolded", "ShootingStar", "ShoppingBag", "ShoppingBagOpen", "ShoppingCart",
    "ShoppingCartSimple", "Shovel", "Shower", "Shrimp", "Shuffle", "ShuffleAngular", "ShuffleSimple", "Sidebar", "SidebarSimple", "Sigma",
    "SignIn", "SignOut", "Signature", "Signpost", "SimCard", "Siren", "SketchLogo", "SkipBack", "SkipBackCircle", "SkipForward",
    "SkipForwardCircle", "Skull", "SkypeLogo", "SlackLogo", "Sliders", "SlidersHorizontal", "Slideshow", "Smiley", "SmileyAngry", "SmileyBlank",
    "SmileyMeh", "SmileyMelting", "SmileyNervous", "SmileySad", "SmileySticker", "SmileyWink", "SmileyXEyes", "SnapchatLogo", "Sneaker", "SneakerMove",
    "Snowflake", "SoccerBall", "Sock", "SolarPanel", "SolarRoof", "SortAscending", "SortDescending", "SoundcloudLogo", "Spade", "Sparkle",
    "SpeakerHifi", "SpeakerHigh", "SpeakerLow", "SpeakerNone", "SpeakerSimpleHigh", "SpeakerSimpleLow", "SpeakerSimpleNone", "SpeakerSimpleSlash", "SpeakerSimpleX", "SpeakerSlash",
    "SpeakerX", "Speedometer", "Sphere", "Spinner", "SpinnerBall", "SpinnerGap", "Spiral", "SplitHorizontal", "SplitVertical", "SpotifyLogo",
    "SprayBottle", "Square", "SquareHalf", "SquareHalfBottom", "SquareLogo", "SquareSplitHorizontal", "SquareSplitVertical", "SquaresFour", "Stack", "StackMinus",
    "StackOverflowLogo", "StackPlus", "StackSimple", "Stairs", "Stamp", "StandardDefinition", "Star", "StarAndCrescent", "StarFour", "StarHalf",
    "StarOfDavid", "SteamLogo", "SteeringWheel", "Steps", "Stethoscope", "Sticker", "Stool", "Stop", "StopCircle", "Storefront",
    "Strategy", "StripeLogo", "Student", "SubsetOf", "SubsetProperOf", "Subtitles", "SubtitlesSlash", "Subtract", "SubtractSquare", "Subway",
    "Suitcase", "SuitcaseRolling", "SuitcaseSimple", "Sun", "SunDim", "SunHorizon", "Sunglasses", "SupersetOf", "SupersetProperOf", "Swap",
    "Swatches", "SwimmingPool", "Sword", "Synagogue", "Syringe", "TShirt", "Table", "Tabs", "Tag", "TagChevron",
    "TagSimple", "Target", "Taxi", "TeaBag", "TelegramLogo", "Television", "TelevisionSimple", "TennisBall", "Tent", "Terminal",
    "TerminalWindow", "TestTube", "TextAUnderline", "TextAa", "TextAlignCenter", "TextAlignJustify", "TextAlignLeft", "TextAlignRight", "TextB", "TextColumns",
    "TextH", "TextHFive", "TextHFour", "TextHOne", "TextHSix", "TextHThree", "TextHTwo", "TextIndent", "TextItalic", "TextOutdent",
    "TextStrikethrough", "TextSubscript", "TextSuperscript", "TextT", "TextTSlash", "TextUnderline", "Textbox", "Thermometer", "ThermometerCold", "ThermometerHot",
    "ThermometerSimple", "ThreadsLogo", "ThreeD", "ThumbsDown", "ThumbsUp", "Ticket", "TidalLogo", "TiktokLogo", "Tilde", "Timer",
    "TipJar", "Tipi", "Tire", "ToggleLeft", "ToggleRight", "Toilet", "ToiletPaper", "Toolbox", "Tooth", "Tornado",
    "Tote", "ToteSimple", "Towel", "Tractor", "Trademark", "TrademarkRegistered", "TrafficCone", "TrafficSign", "TrafficSignal", "Train",
    "TrainRegional", "TrainSimple", "Tram", "Translate", "Trash", "TrashSimple", "Tray", "TrayArrowDown", "TrayArrowUp", "TreasureChest",
    "Tree", "TreeEvergreen", "TreePalm", "TreeStructure", "TreeView", "TrendDown", "TrendUp", "Triangle", "TriangleDashed", "Trolley",
    "TrolleySuitcase", "Trophy", "Truck", "TruckTrailer", "TumblrLogo", "TwitchLogo", "TwitterLogo", "Umbrella", "UmbrellaSimple", "Union",
    "Unite", "UniteSquare", "Upload", "UploadSimple", "Usb", "User", "UserCheck", "UserCircle", "UserCircleCheck", "UserCircleDashed",
    "UserCircleGear", "UserCircleMinus", "UserCirclePlus", "UserFocus", "UserGear", "UserList", "UserMinus", "UserPlus", "UserRectangle", "UserSound",
    "UserSquare", "UserSwitch", "Users", "UsersFour", "UsersThree", "Van", "Vault", "VectorThree", "VectorTwo", "Vibrate",
    "Video", "VideoCamera", "VideoCameraSlash", "VideoConference", "Vignette", "VinylRecord", "VirtualReality", "Virus", "Visor", "Voicemail",
    "Volleyball", "Wall", "Wallet", "Warehouse", "Warning", "WarningCircle", "WarningDiamond", "WarningOctagon", "WashingMachine", "Watch",
    "WaveSawtooth", "WaveSine", "WaveSquare", "WaveTriangle", "Waveform", "WaveformSlash", "Waves", "Webcam", "WebcamSlash", "WebhooksLogo",
    "WechatLogo", "WhatsappLogo", "Wheelchair", "WheelchairMotion", "WifiHigh", "WifiLow", "WifiMedium", "WifiNone", "WifiSlash", "WifiX",
    "Wind", "Windmill", "WindowsLogo", "Wine", "Wrench", "X", "XCircle", "XLogo", "XSquare", "Yarn",
    "YinYang", "YoutubeLogo",
})


def _fix_phosphor_imports(app_jsx: str) -> str:
    """Strip any phosphor icon names not in the verified whitelist — prevents 'X is not exported' build errors."""
    phosphor_pattern = re.compile(
        r"^(import\s*\{)([^}]+)(\}\s*from\s*['\"]@phosphor-icons/react['\"];?)",
        re.MULTILINE,
    )
    def _filter_icons(m: re.Match) -> str:
        raw_names = [n.strip() for n in m.group(2).split(",") if n.strip()]
        valid = [n for n in raw_names if n in _VALID_PHOSPHOR_ICONS]
        invalid = [n for n in raw_names if n not in _VALID_PHOSPHOR_ICONS]
        if invalid:
            print(f"[demo] Removed invalid phosphor icons: {invalid}")
        if not valid:
            return ""  # remove the entire import line
        return f"{m.group(1)} {', '.join(valid)} {m.group(3)}"
    result = phosphor_pattern.sub(_filter_icons, app_jsx)
    # Remove any usage of removed icons in JSX (replace <BadIcon with <Star)
    return result


def _design_qa_fix(
    app_jsx: str,
    design_brief: str,
    design_system: str,
    conn,
    lead_id: int,
    generation_num: int = 1,
) -> str:
    """
    Python-based design quality checks + targeted Sonnet fix if violations found.
    Checks creative/visual rules that _post_process_jsx only warns about.
    Only fires a fix call when high-confidence violations are detected.
    """
    violations: list[str] = []

    # 1. Banned font imported — check @import lines specifically
    import_lines = [l for l in app_jsx.split("\n") if "@import" in l]
    import_block = "\n".join(import_lines)
    for banned in ["Inter", "Roboto", "Arial", "Open Sans"]:
        if banned in import_block:
            violations.append(
                f"FONT: '{banned}' is imported — replace with a premium Google Font from the design brief "
                f"(Cabinet Grotesk, Outfit, Satoshi, Plus Jakarta Sans, DM Sans, etc). "
                f"Never use generic system fonts as primary typeface."
            )

    # 2. No Google Fonts import at all
    if not any("fonts.googleapis.com" in l or "@import url" in l for l in import_lines):
        violations.append(
            "FONT: No Google Fonts @import found anywhere. Must import 2 fonts via @import in a <style> tag "
            "at the top of the component. Example: @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap')"
        )

    # 3. Brief hex colors absent from generated code
    brief_hexes = re.findall(r'#([0-9a-fA-F]{6})\b', design_brief)
    if brief_hexes:
        unique_hexes = list(dict.fromkeys(h.upper() for h in brief_hexes))
        missing = [f"#{h}" for h in unique_hexes[:4] if f"#{h}" not in app_jsx.upper()]
        if len(missing) >= 2:
            violations.append(
                f"COLOR: Brief specified these exact hex colors: {', '.join(missing[:3])} — none appear in the code. "
                f"The design brief colors are mandatory. Do NOT use generic blue/purple. Apply the brief palette to "
                f"backgrounds, accents, CTA buttons, and highlights."
            )

    # 4. Animation variety — all sections use identical initial state
    initial_patterns = re.findall(r'initial=\{\{([^}]+)\}\}', app_jsx)
    unique_initials = set(p.strip() for p in initial_patterns)
    if len(initial_patterns) > 4 and len(unique_initials) < 2:
        violations.append(
            f"ANIMATION: {len(initial_patterns)} scroll animations all use the same initial state. "
            "This is the #1 AI-slop signal. Each major section MUST use a different animation technique: "
            "blur-emerge, slide-from-left, spring-pop, clip-path-wipe, curtain-cascade, scale-reveal, etc. "
            "Never repeat the same initial={{opacity:0,y:32}} pattern across all sections."
        )

    # 5. Hero has no full-bleed background image
    # Check first 5000 chars of the JSX for hero section markers
    jsx_lower = app_jsx.lower()
    hero_area_end = max(jsx_lower.find("leistungen"), jsx_lower.find("services"), 4000)
    hero_area = app_jsx[:hero_area_end]
    has_cover = "object-cover" in hero_area or "objectfit" in hero_area.lower() or "objectFit" in hero_area
    has_absolute_inset = ("absolute" in hero_area and ("inset-0" in hero_area or "inset: 0" in hero_area or "inset:0" in hero_area))
    if not has_cover and not has_absolute_inset:
        violations.append(
            "HERO: Hero section appears to be missing a full-bleed background image. "
            "The hero MUST have a position:absolute inset:0 object-cover background image filling the entire viewport. "
            "Text overlaid on a dark scrim (gradient or rgba). Never a side-by-side image. "
            "Use a real lead image if available, otherwise: https://picsum.photos/seed/{descriptive-keyword}/1920/1080"
        )

    if not violations:
        print("[demo] Design QA: PASS — no violations found")
        return app_jsx

    print(f"[demo] Design QA: {len(violations)} violations — running Sonnet fix pass:")
    for v in violations:
        print(f"  ⚠ {v[:120]}")

    violations_text = "\n".join(f"- {v}" for v in violations)
    fix_prompt = (
        f"The App.jsx below has CRITICAL design quality violations. Fix ONLY these issues — "
        f"do NOT restructure, rewrite sections, or remove any existing content:\n\n"
        f"{violations_text}\n\n"
        f"Output the complete corrected App.jsx. No markdown fences, no explanation, start with import statements.\n\n"
        f"App.jsx:\n{app_jsx}"
    )

    fixed = claude_p(
        prompt=fix_prompt,
        system=design_system,
        model="claude-sonnet-4-6",
        max_tokens=40000,
        conn=conn,
        lead_id=lead_id,
        stage="design_qa_fix",
        generation_num=generation_num,
    )
    fixed = fixed.strip()
    if fixed.startswith("```"):
        fixed = re.sub(r'^```[^\n]*\n', '', fixed)
        fixed = re.sub(r'\n```$', '', fixed)
    print("[demo] Design QA fix pass complete")
    return fixed


def _validate_and_fix_jsx(app_jsx: str, conn=None, lead_id: int = 0) -> str:
    """
    Quick pre-flight: Python checks first, Haiku only if issues found.
    Fixes the most common Vite build failure causes.
    """
    # Always deduplicate React imports first (no LLM call needed)
    app_jsx = _dedup_react_imports(app_jsx)
    # Strip hallucinated phosphor icon names
    app_jsx = _fix_phosphor_imports(app_jsx)

    issues = []
    if not app_jsx.strip().startswith("import"):
        issues.append("File does not start with import statements")
    if "export default function App" not in app_jsx:
        issues.append("Missing: export default function App()")
    if app_jsx.count(' class="') > 0:
        issues.append(f"Found {app_jsx.count(' class=\"')} instances of class= (must be className=)")

    if not issues:
        return app_jsx

    print(f"[demo] JSX validation found issues: {issues} — calling Haiku to fix...")
    prompt = (
        f"Fix the following issues in this React App.jsx file and return the complete corrected file.\n"
        f"Issues found:\n" + "\n".join(f"- {i}" for i in issues) + "\n\n"
        f"Rules:\n"
        f"- Return ONLY valid JSX, no markdown fences, no explanation\n"
        f"- Fix class= → className=\n"
        f"- React hooks: use `import {{ useState, useEffect }} from 'react'` (no duplicate React imports)\n"
        f"- Ensure export default function App() is present\n\n"
        f"File:\n{app_jsx}"
    )
    fixed = claude_p(
        prompt=prompt,
        model="claude-haiku-4-5",
        max_tokens=20000,
        conn=conn,
        lead_id=lead_id,
        stage="jsx_validation",
    )
    fixed = fixed.strip()
    if fixed.startswith("```"):
        fixed = re.sub(r'^```[^\n]*\n', '', fixed)
        fixed = re.sub(r'\n```$', '', fixed)
    return fixed


def _setup_demo_dir(demo_dir: Path) -> None:
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
    shutil.copytree(TEMPLATE_DIR, demo_dir)
    (demo_dir / "src").mkdir(exist_ok=True)


def _deploy_via_vercel_api(demo_dir: Path, slug: str, conn, lead_id: int) -> str | None:
    """Upload React source to Vercel API — Vercel builds in their cloud, no local npm needed."""
    token = os.environ.get("VERCEL_TOKEN", "")
    if not token:
        print("[demo] VERCEL_TOKEN not set")
        return None

    _set_sub_stage(conn, lead_id, "vercel_deploy")

    # Collect all source files (skip node_modules / dist if they exist)
    files = []
    skip = {"node_modules", "dist", ".git"}
    for path in demo_dir.rglob("*"):
        if path.is_file() and not any(p in skip for p in path.parts):
            rel = path.relative_to(demo_dir).as_posix()
            try:
                files.append({"file": rel, "data": path.read_text(encoding="utf-8")})
            except UnicodeDecodeError:
                import base64
                files.append({"file": rel, "data": base64.b64encode(path.read_bytes()).decode(), "encoding": "base64"})

    payload = {
        "name": f"lead-{slug}",
        "files": files,
        "projectSettings": {
            "buildCommand": "npm run build",
            "outputDirectory": "dist",
            "installCommand": "npm install",
            "framework": None,
        },
        "target": "production",
    }

    try:
        resp = httpx.post(
            "https://api.vercel.com/v13/deployments",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        data = resp.json()
        if resp.status_code not in (200, 201):
            print(f"[demo] vercel API error {resp.status_code}: {json.dumps(data)[:500]}")
            return None

        deploy_id = data.get("id") or ""
        url = data.get("url") or ""
        if url and not url.startswith("https://"):
            url = f"https://{url}"
        print(f"[demo] vercel deployment created: {url} (id={deploy_id}) — waiting for build...")

        # Poll build status — Vercel builds asynchronously after returning 200
        headers = {"Authorization": f"Bearer {token}"}
        for attempt in range(24):  # max ~4 min (24 × 10s)
            import time
            time.sleep(10)
            try:
                status_resp = httpx.get(
                    f"https://api.vercel.com/v13/deployments/{deploy_id}",
                    headers=headers,
                    timeout=30,
                )
                status_data = status_resp.json()
                state = status_data.get("readyState") or status_data.get("state") or "UNKNOWN"
                print(f"[demo] vercel build status [{attempt+1}/24]: {state}")

                if state in ("READY", "ready"):
                    print(f"[demo] vercel deploy ok: {url}")
                    return url or None

                if state in ("ERROR", "CANCELED", "error", "canceled"):
                    # Fetch build error details
                    try:
                        err_resp = httpx.get(
                            f"https://api.vercel.com/v3/deployments/{deploy_id}/events",
                            headers=headers,
                            params={"types": "stdout,stderr,error", "limit": "100"},
                            timeout=30,
                        )
                        events = err_resp.json()
                        if isinstance(events, list):
                            error_lines = [
                                e.get("payload", {}).get("text", "") or e.get("text", "")
                                for e in events if isinstance(e, dict)
                            ]
                            error_text = "\n".join(l for l in error_lines if l)[:2000]
                            print(f"[demo] vercel BUILD FAILED — error log:\n{error_text}")
                        else:
                            print(f"[demo] vercel BUILD FAILED: {json.dumps(status_data.get('error', {}))[:500]}")
                    except Exception as log_err:
                        print(f"[demo] vercel BUILD FAILED (could not fetch logs: {log_err})")
                    return None

            except Exception as poll_err:
                print(f"[demo] vercel status poll error: {poll_err}")
                continue

        print(f"[demo] vercel build timeout after 4 min — url may still become ready: {url}")
        return url or None

    except Exception as e:
        print(f"[demo] vercel API exception: {e}")
    return None


def generate_demo(lead: dict, conn) -> str | None:
    """
    Full demo generation pipeline for a single lead.
    Returns the deployed demo URL, or None on failure.
    """
    lead_id = lead["id"]
    slug = _make_slug(lead)
    demo_dir = DATA_DIR / slug

    # Compute generation number (how many times has this lead been generated before)
    gen_row = conn.execute(
        "SELECT COUNT(DISTINCT generation_num) FROM cost_log WHERE lead_id=? AND stage='demo_gen'",
        (lead_id,),
    ).fetchone()
    generation_num = (gen_row[0] or 0) + 1

    # Stage 1: Scrape existing website
    _set_sub_stage(conn, lead_id, "scraping")
    content: dict = {}
    if lead.get("website"):
        content = asyncio.run(scrape_website_content(lead["website"]))
        if content.get("error"):
            print(f"[demo] scraping error for lead {lead_id}: {content['error']}")
        else:
            print(f"[demo] scraped lead {lead_id}: {len(content.get('raw_text',''))} chars, {len(content.get('subpage_text',''))} subpage chars, {len(content.get('images',[]))} images")
        (DATA_DIR / slug).mkdir(parents=True, exist_ok=True)
        (DATA_DIR / slug / "content.json").write_text(
            json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        content = {
            "raw_text": "", "services": [], "contact": {}, "nav_items": [],
            "testimonials": [], "images": [], "bg_images": [],
        }

    # Stage 2: Reference site data — all 3 sites cached, 2 randomly selected per demo
    category = lead.get("category", "")
    all_ref_sites = get_all_reference_data(category)
    selected_sites = random.sample(all_ref_sites, min(2, len(all_ref_sites))) if all_ref_sites else []
    ref_css = selected_sites[0].get("css", {}) if selected_sites else {}

    # Stage 3: Category design inspiration (cached 7 days)
    _set_sub_stage(conn, lead_id, "inspiration")
    inspiration = get_inspiration_notes(category=category, conn=conn, lead_id=lead_id)

    # Stage 4: Haiku — structured content extraction
    _set_sub_stage(conn, lead_id, "content_extraction")
    print(f"[demo] Extracting structured content for lead {lead_id}...")
    structured = _extract_structured_content(
        raw_text=content.get("raw_text", ""),
        subpage_text=content.get("subpage_text", ""),
        category=category,
        conn=conn,
        lead_id=lead_id,
        generation_num=generation_num,
    )

    # Stage 5: Sonnet — design brief (Sonnet understands design intent better than Haiku)
    _set_sub_stage(conn, lead_id, "design_brief")
    print(f"[demo] Generating design brief for lead {lead_id}...")
    # Pick animation assignments + palette once — shared between brief (Sonnet) and codegen (Fable)
    style_profile = _get_style_profile(category)
    picked_animations = _pick_animations(category, k=style_profile["k"])
    suggested_palette = _get_suggested_palette(category, seed=lead.get("name", "") + lead.get("website", ""))
    scraped_colors = content.get("colors") or []

    ref_design_analyses = [s.get("design_analysis") for s in selected_sites if s.get("design_analysis")]

    design_brief = claude_p(
        prompt=_build_design_brief_prompt(
            lead, inspiration, ref_css, structured,
            content.get("design_analysis"), picked_animations,
            scraped_colors=scraped_colors,
            suggested_palette=suggested_palette,
            ref_design_analyses=ref_design_analyses or None,
            style_profile=style_profile,
        ),
        system=_BRIEF_SYSTEM_PROMPT,
        model="claude-opus-4-8",
        max_tokens=1200,
        conn=conn,
        lead_id=lead_id,
        stage="design_brief",
        generation_num=generation_num,
    )
    print(f"[demo] design_brief:\n{design_brief}")

    # Stage 6: Design system prompt (skills)
    design_system = build_design_system_prompt()

    # Stage 7: Build images list — 2 randomly selected ref sites × 3 shots + 2 lead shots
    ref_screenshots: list[str] = []
    for site_data in selected_sites:
        ref_screenshots.extend(site_data.get("screenshots", [])[:3])

    lead_screenshots = content.get("screenshots") or (
        [content["screenshot_b64"]] if content.get("screenshot_b64") else []
    )
    images: list[tuple[str, str]] = [
        (b64, "image/jpeg") for b64 in ref_screenshots + lead_screenshots if b64
    ]

    # Stage 8: Sonnet — generate App.jsx (streamed for real-time progress visibility)
    _set_sub_stage(conn, lead_id, "generating_jsx")
    print(f"[demo] Generating App.jsx with Sonnet for lead {lead_id} ({len(images)} images)...")

    import time as _time
    _jsx_progress_ts = [_time.time()]

    def _jsx_progress(char_count: int) -> None:
        now = _time.time()
        if now - _jsx_progress_ts[0] >= 3.0:
            approx_tokens = char_count // 4
            _set_sub_stage(conn, lead_id, f"generating_jsx:{approx_tokens}")
            _jsx_progress_ts[0] = now

    prompt = _build_codegen_prompt(
        lead=lead,
        content=content,
        structured=structured,
        inspiration=inspiration,
        design_brief=design_brief,
        slug=slug,
        n_ref_screenshots=len(ref_screenshots),
        n_lead_screenshots=len(lead_screenshots),
        picked_animations=picked_animations,
    )

    app_jsx = claude_p(
        prompt=prompt,
        system=design_system,
        model="claude-sonnet-4-6",
        max_tokens=48000,
        conn=conn,
        lead_id=lead_id,
        stage="demo_gen",
        images=images if images else None,
        generation_num=generation_num,
        on_progress=_jsx_progress,
    )

    # Strip accidental markdown fences
    app_jsx = app_jsx.strip()
    if app_jsx.startswith("```"):
        app_jsx = re.sub(r'^```[^\n]*\n', '', app_jsx)
        app_jsx = re.sub(r'\n```$', '', app_jsx)

    # Post-process: auto-fix banned patterns + brief compliance check
    app_jsx, _post_warnings = _post_process_jsx(app_jsx, design_brief)

    # Warn if output was truncated at the token cap
    approx_out_tokens = len(app_jsx) // 4
    if approx_out_tokens >= 31000:
        print(f"[demo] WARNING: output ~{approx_out_tokens} tokens — may be truncated at 32k limit")

    # Stage 8.5: Haiku — JSX pre-flight validation (syntax)
    _set_sub_stage(conn, lead_id, "jsx_validation")
    app_jsx = _validate_and_fix_jsx(app_jsx, conn=conn, lead_id=lead_id)

    # Stage 8.6: Design QA — check creative directives, Sonnet fix if violations found
    _set_sub_stage(conn, lead_id, "design_qa")
    app_jsx = _design_qa_fix(
        app_jsx=app_jsx,
        design_brief=design_brief,
        design_system=design_system,
        conn=conn,
        lead_id=lead_id,
        generation_num=generation_num,
    )

    # Stage 9: Set up React project and write App.jsx
    _setup_demo_dir(demo_dir)
    (demo_dir / "src" / "App.jsx").write_text(app_jsx, encoding="utf-8")

    # Save JSX to DB so it can be retrieved/edited without Railway filesystem access
    conn.execute("UPDATE leads SET demo_jsx=? WHERE id=?", (app_jsx, lead_id))
    conn.commit()

    # Stage 10+11: Deploy source to Vercel (Vercel builds in their cloud)
    demo_url = _deploy_via_vercel_api(demo_dir, slug, conn, lead_id)

    if demo_url:
        conn.execute(
            "UPDATE leads SET demo_url=?, demo_generated_at=datetime('now'),"
            " stage='ready_for_review', updated_at=datetime('now') WHERE id=?",
            (demo_url, lead_id),
        )
    else:
        conn.execute(
            "UPDATE leads SET stage='demo_deploy_failed', updated_at=datetime('now') WHERE id=?",
            (lead_id,),
        )
    conn.commit()

    return demo_url
