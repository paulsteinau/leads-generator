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

    prompt = (
        f"Extract structured information from this German {category} business website text.\n\n"
        f"Return ONLY valid JSON with these fields:\n"
        f"- services: list of strings, each a service or offering (max 10, keep original German wording)\n"
        f"- about: 2-3 sentence summary of who this business is, their story, USPs (in German)\n"
        f"- testimonials: list of customer quote strings found verbatim (max 5)\n"
        f"- phone: phone number string or null\n"
        f"- email: email address string or null\n"
        f"- opening_hours: string description if found, else null\n\n"
        f"Website text:\n{combined}"
    )

    raw = claude_p(
        prompt=prompt,
        model="claude-sonnet-4-6",
        max_tokens=1200,
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
    "Asymmetric Split Hero — text on one side, hero image on the other, bold headline left-aligned",
    "Scroll-Pinned Hero — hero stays pinned while content slides up behind it (GSAP pin)",
    "Editorial Manifesto Hero — large kinetic type, no asset, almost-poster feel",
    "Full-Bleed Photo Hero — edge-to-edge image, text overlay with scrim, bold single headline",
    "Curtain-Reveal Hero — parts animate in on load like a curtain parting",
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
                      "Immobilienmakler", "Unternehmensberater", "Wirtschaftsprüfer", "Notariat"}
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
    {"name": "Legal Navy",      "bg": "#080f1a", "surface": "#0d1a2e", "text": "#f0ebe0", "accent": "#c4a35a", "shadow": "#030810"},
    {"name": "Forest Authority","bg": "#0c1a12", "surface": "#132318", "text": "#edf0e8", "accent": "#8aab7a", "shadow": "#060d08"},
    {"name": "Barrister Ivory", "bg": "#f6f2eb", "surface": "#ffffff", "text": "#161410", "accent": "#7a5c2e", "shadow": "#ddd8cc"},
    {"name": "Charcoal Edit",   "bg": "#111111", "surface": "#1c1c1c", "text": "#e8e4db", "accent": "#a08060", "shadow": "#080808"},
]

_PALETTES_MEDICAL = [
    {"name": "Clinical Light",  "bg": "#f8fafc", "surface": "#ffffff", "text": "#0f1e30", "accent": "#2c6e8a", "shadow": "#d4e0ea"},
    {"name": "Warm Care",       "bg": "#fdfaf5", "surface": "#ffffff", "text": "#1c1812", "accent": "#4e7a6a", "shadow": "#e4ddd0"},
    {"name": "Deep Medical",    "bg": "#0a1520", "surface": "#0f2030", "text": "#e8f0f8", "accent": "#4ab8c8", "shadow": "#050c14"},
    {"name": "Sage Practice",   "bg": "#f4f7f4", "surface": "#ffffff", "text": "#141e18", "accent": "#3d7060", "shadow": "#d8e4dc"},
]

_PALETTES_LIGHT_TRADE = [
    {"name": "Soft Studio",     "bg": "#faf8f5", "surface": "#ffffff", "text": "#1c1814", "accent": "#9b6e5c", "shadow": "#e4ddd6"},
    {"name": "Clean Nordic",    "bg": "#f5f7f8", "surface": "#ffffff", "text": "#141c24", "accent": "#5c7a8a", "shadow": "#d8e0e8"},
    {"name": "Warm Craft",      "bg": "#fdf8f2", "surface": "#ffffff", "text": "#1e1810", "accent": "#8c6840", "shadow": "#e8e0d4"},
]

_PALETTES_PLAYFUL = [
    {"name": "Ink Dark",        "bg": "#0a0a0c", "surface": "#131318", "text": "#f0eeea", "accent": "#e85c3a", "shadow": "#050508"},
    {"name": "Studio Night",    "bg": "#0f0e14", "surface": "#1a1824", "text": "#eceaf8", "accent": "#9b70e0", "shadow": "#08070e"},
    {"name": "Raw Industrial",  "bg": "#111110", "surface": "#1c1c1a", "text": "#f0ede6", "accent": "#d4a030", "shadow": "#080806"},
    {"name": "Deep Crimson",    "bg": "#0e0a0a", "surface": "#1c1212", "text": "#f4ede8", "accent": "#c43030", "shadow": "#080404"},
]

_CATEGORY_TO_PALETTE_BUCKET = {
    # formal
    "Anwalt": _PALETTES_FORMAL, "Rechtsanwalt": _PALETTES_FORMAL,
    "Notar": _PALETTES_FORMAL, "Notariat": _PALETTES_FORMAL,
    "Steuerberater": _PALETTES_FORMAL, "Wirtschaftsprüfer": _PALETTES_FORMAL,
    "Unternehmensberater": _PALETTES_FORMAL, "Immobilienmakler": _PALETTES_FORMAL,
    "Architekt": _PALETTES_FORMAL,
    # medical
    "Arzt": _PALETTES_MEDICAL, "Kinderarzt": _PALETTES_MEDICAL,
    "Zahnarzt": _PALETTES_MEDICAL, "Physiotherapeut": _PALETTES_MEDICAL,
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


def _get_suggested_palette(category: str) -> dict | None:
    bucket = _CATEGORY_TO_PALETTE_BUCKET.get(category)
    return random.choice(bucket) if bucket else None


# Formal-category premium design rules injected into the brief prompt
_FORMAL_PREMIUM_RULES = """
FORMAL PROFESSION — PREMIUM DESIGN RULES (non-negotiable):
- Typography: serif heading (Fraunces, Playfair Display, or Cormorant Garamond) + clean sans body. No sans-only pairing.
- Color: stay within the suggested palette. Accent must be muted metallic (gold, brass, sage, bronze) — never neon, blue, or purple.
- Imagery: architectural detail shots, texture close-ups, office/material photography. NO smiling stock people.
- Layout: editorial and structured. No bento grids, no card-stack chaos. Clean hierarchy only.
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
- Shadows tinted to match background hue — never pure rgba(0,0,0,0.3)
- ONE gray family only (warm OR cool) — never mix warm and cool grays in the same design
- Flat solid background is sterile — specify one of: subtle radial gradient, CSS noise overlay (opacity 0.02-0.04), or mesh gradient

FONTS:
- Banned: Inter, Roboto, Arial, Open Sans, Helvetica
- Sans options: Geist, Outfit, Cabinet Grotesk, Satoshi, Plus Jakarta Sans, Raleway, Syne, DM Sans
- Traditional professions (Anwalt, Notar, Arzt, Steuerberater, Architekt): consider a serif heading (Fraunces, Playfair Display, Cormorant Garamond) paired with a clean sans body

MOOD ADJECTIVES:
- Must be specific to this exact business — never generic AI defaults
- Banned: elegant, modern, professionell, innovativ, nahtlos, vertrauenswürdig, hochwertig
- Good examples: handwerklich + bodenständig + ehrlich / urban + präzise + direkt / warm + familiär + verlässlich

Output ONLY the requested brief fields. No preamble, no markdown headers, no explanation."""


def _build_design_brief_prompt(lead: dict, inspiration: str, ref_css: dict, structured: dict | None = None, design_analysis: dict | None = None, picked_animations: list | None = None, scraped_colors: list | None = None, suggested_palette: dict | None = None, ref_design_analyses: list | None = None) -> str:
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
    if category in _LIGHT_MODE_CATEGORIES:
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
        f"- Confirm animation assignments: list each section + technique in one word\n\n"
        f"Max 220 words. These values go directly into React/CSS code — be precise."
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

    # 7. Template placeholder comments inside JSX that break the build:
    #    {/* image or content block */} etc. left verbatim from code snippets
    placeholder_count = len(re.findall(r'\{/\*\s*(?:image|content block|item content|card|heading|scrolling content)[^*]*\*/\}', jsx, re.IGNORECASE))
    if placeholder_count:
        jsx = re.sub(r'\{/\*\s*(?:image|content block|item content|card|heading|scrolling content)[^*]*\*/\}', '{null}', jsx, flags=re.IGNORECASE)
        warnings.append(f"AUTO-FIXED: {placeholder_count} empty placeholder comments replaced with {{null}}")

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
        routes.append({"url": url, "path": f"/{route_slug}", "label": label})

    routes_section = ""
    if routes:
        route_lines = "\n".join(
            f'  - path="{r["path"]}" label="{r["label"]}" (content from: {r["url"]})'
            for r in routes
        )
        routes_section = f"""
## Subpages to Implement as React Router Routes
The existing website has these subpages — each must become a real route:
{route_lines}

Route "/" is the home/landing page (full marketing page with hero, key sections, CTA).
Each subpage route renders its own dedicated page component with full content from the scraped data.
The Nav must link to all routes and show the active route visually.
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
            for i in scraped_images[:6]
            if i.get("src", "").startswith("http")
        )
        bg_lines = "\n".join(f'  background-image: url("{u}")' for u in bg_images[:3])
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
            screenshot_lines.append(f"Image {idx}: Reference site — {label}. Study the design quality, typography, spacing, and color use.")
            idx += 1
    if n_lead_screenshots > 0:
        lead_labels = ["hero/nav area", "mid section"]
        for i in range(n_lead_screenshots):
            label = lead_labels[i] if i < len(lead_labels) else f"section {i+1}"
            screenshot_lines.append(f"Image {idx}: Current lead website — {label}. Dramatically improve this while keeping all real content.")
            idx += 1
    screenshot_context = "\n".join(screenshot_lines) + "\n\n" if screenshot_lines else ""

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

    return f"""
{animation_checklist}
{screenshot_context}Generate a complete single-file React App.jsx for this German business demo website.
{routes_section}

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

{weakness_section}

## Design Brief (implement exactly)
{design_brief}

## Category Design Inspiration
{inspiration}

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
- If no subpages found: build a single-page app without router, just scroll sections

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
                            params={"types": "error,stderr", "limit": "20"},
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
    picked_animations = _pick_animations(category, k=6)
    suggested_palette = _get_suggested_palette(category)
    scraped_colors = content.get("colors") or []

    ref_design_analyses = [s.get("design_analysis") for s in selected_sites if s.get("design_analysis")]

    design_brief = claude_p(
        prompt=_build_design_brief_prompt(
            lead, inspiration, ref_css, structured,
            content.get("design_analysis"), picked_animations,
            scraped_colors=scraped_colors,
            suggested_palette=suggested_palette,
            ref_design_analyses=ref_design_analyses or None,
        ),
        system=_BRIEF_SYSTEM_PROMPT,
        model="claude-sonnet-4-6",
        max_tokens=700,
        conn=conn,
        lead_id=lead_id,
        stage="design_brief",
        generation_num=generation_num,
    )

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

    # Stage 8: Opus — generate App.jsx
    _set_sub_stage(conn, lead_id, "generating_jsx")
    print(f"[demo] Generating App.jsx with Opus for lead {lead_id} ({len(images)} images)...")
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
        model="claude-fable-5",
        max_tokens=40000,
        conn=conn,
        lead_id=lead_id,
        stage="demo_gen",
        images=images if images else None,
        generation_num=generation_num,
    )

    # Strip accidental markdown fences
    app_jsx = app_jsx.strip()
    if app_jsx.startswith("```"):
        app_jsx = re.sub(r'^```[^\n]*\n', '', app_jsx)
        app_jsx = re.sub(r'\n```$', '', app_jsx)

    # Post-process: auto-fix banned patterns + brief compliance check
    app_jsx, _post_warnings = _post_process_jsx(app_jsx, design_brief)

    # Warn if output was exactly max_tokens — likely truncated
    approx_out_tokens = len(app_jsx) // 4
    if approx_out_tokens >= 39000:
        print(f"[demo] WARNING: Fable output ~{approx_out_tokens} tokens — may be truncated even at 40k limit")

    # Stage 8.5: Haiku — JSX pre-flight validation
    _set_sub_stage(conn, lead_id, "jsx_validation")
    app_jsx = _validate_and_fix_jsx(app_jsx, conn=conn, lead_id=lead_id)

    # Stage 9: Set up React project and write App.jsx
    _setup_demo_dir(demo_dir)
    (demo_dir / "src" / "App.jsx").write_text(app_jsx, encoding="utf-8")

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
