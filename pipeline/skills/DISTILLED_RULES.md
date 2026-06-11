# 50 Distilled Demo-Generation Rules

Extracted from all 6 design skills. Ranked by impact on real customer perception.
Rules already in `_BASE_PROMPT` are marked **[IN PROMPT]**.
Rules missing from `_BASE_PROMPT` are marked **[MISSING — ADD]**.

---

## TYPOGRAPHY (5)

1. **[IN PROMPT]** BANNED fonts: Inter, Roboto, Arial, Open Sans, Helvetica. Use Geist, Outfit, Cabinet Grotesk, Satoshi, Plus Jakarta Sans — imported via `@import` in a `<style>` tag at top of App.jsx.

2. **[IN PROMPT]** Hero H1 must NEVER exceed 2-3 lines at desktop. Use `max-w-5xl` or `max-w-6xl` on the heading container and `clamp(3rem, 5vw, 5.5rem)` font-size. Wider container + smaller type beats narrow container + big type.

3. **[MISSING — ADD]** `text-wrap: balance` on all headings. Prevents single orphaned words on the last line. No exceptions.

4. **[MISSING — ADD]** Letter-spacing: negative (`tracking-tight` or `tracking-tighter`) on large display headers. Positive (`tracking-[0.15em]` to `tracking-[0.25em]`) on small uppercase labels. Never default tracking on both.

5. **[IN PROMPT]** Eyebrow labels: max 1 per 3 sections (hero counts as 1). Format: `rounded-full px-3 py-1 text-[10px] uppercase tracking-[0.2em] font-medium`. If you've already used one in the last section, skip it.

---

## ANIMATION — CORE (8)

6. **[IN PROMPT]** Every section entry must animate on scroll — no element appears statically. Pattern: `initial={{ opacity: 0, y: 32 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }}`.

7. **[MISSING — ADD]** ALWAYS custom cubic-bezier — NEVER `linear`, `ease`, `ease-in-out`, `ease-in` built-ins. Specific curves:
   - UI interactions + reveals: `cubic-bezier(0.23, 1, 0.32, 1)`
   - Scroll reveals: `cubic-bezier(0.16, 1, 0.3, 1)` (already in prompt as `[0.16, 1, 0.3, 1]`)
   - Drawers / iOS-feel: `cubic-bezier(0.32, 0.72, 0, 1)`
   - `ease-in` is BANNED on all UI — it starts slow, looks unresponsive

8. **[IN PROMPT]** NEVER animate from `scale(0)`. Start from `scale(0.95)` + `opacity: 0`. Nothing in the real world appears from nothing.

9. **[IN PROMPT]** Stagger children: 30-80ms per item. Use `staggerChildren: 0.06` in motion variants. Long stagger (>100ms) makes the page feel slow. Stagger is decorative — never block interaction during it.

10. **[MISSING — ADD]** Asymmetric timing: slow enter (600-800ms duration), fast exit (150-200ms). Applied to modals, drawers, overlays. "Slow where user is deciding, fast where system responds."

11. **[IN PROMPT]** All buttons: `whileTap={{ scale: 0.97 }}`. Physical press feedback is mandatory on every clickable element.

12. **[IN PROMPT]** `useReducedMotion()` wraps all animations. When true: `duration: 0` or skip `y` translate entirely. Keep only opacity fades (they aid comprehension, don't cause motion sickness).

13. **[IN PROMPT]** Only animate `transform` and `opacity`. NEVER animate `top`, `left`, `width`, `height`, `padding`, `margin` — these trigger layout recalculation on every frame.

---

## ANIMATION — ADVANCED GSAP (5)

14. **[IN PROMPT]** NEVER `window.addEventListener('scroll')`. Use `gsap.ScrollTrigger` or `IntersectionObserver`. Scroll listeners cause continuous reflows and kill mobile performance.

15. **[MISSING — ADD]** Image scroll scrubbing with GSAP: images start at `scale: 0.8` → grow to `scale: 1.0` as they enter view → darken and fade (`opacity: 0.2`) as they scroll out of view. Creates cinematic depth.

16. **[IN PROMPT]** Card stacking: `pin: true, pinSpacing: false, scrub: true` — sections overlap and stack on top of each other as user scrolls down.

17. **[MISSING — ADD]** Text reveal: paragraph word opacity scrubs from `0.1` to `1.0` sequentially as user scrolls through the section. Creates engagement and reading momentum.

18. **[IN PROMPT]** Every useEffect with GSAP: `const ctx = gsap.context(() => { ... }); return () => ctx.revert();`. No exceptions — memory leaks kill the demo on repeated renders.

---

## ANIMATION — PERFORMANCE (4)

19. **[MISSING — ADD]** `backdrop-blur` ONLY on fixed or sticky elements (nav pill, modals, overlays). NEVER on scrolling containers or large content areas. Blur on scrolling = continuous GPU repaints = frame drops on every device.

20. **[MISSING — ADD]** Framer Motion hardware acceleration: use `animate={{ transform: "translateX(100px)" }}` NOT `animate={{ x: 100 }}`. The shorthand `x`/`y`/`scale` props run on the main thread via rAF — they drop frames when the browser is busy. Full `transform` string is GPU-accelerated.

21. **[MISSING — ADD]** `will-change: transform` only on elements that are *actively* animating. Set it immediately before the animation starts, remove it immediately after. Using it broadly causes excess memory consumption.

22. **[MISSING — ADD]** CSS transitions (not keyframes) for rapidly-triggered elements (toasts, toggles, hover states). CSS transitions retarget mid-animation; keyframes restart from zero on interruption.

---

## SPRING PHYSICS (2)

23. **[MISSING — ADD]** Spring animations for drag, gesture, and magnetic hover interactions: `{ type: "spring", duration: 0.5, bounce: 0.15 }`. Keep bounce subtle (0.1–0.25). A higher bounce sounds fun; in demos it looks unprofessional.

24. **[MISSING — ADD]** Mouse-tracking / magnetic effects: use `useSpring` from motion/react — direct mouse value updates look mechanical and artificial. Spring adds momentum that mimics real physics.

---

## COLOR & AI-TELL PREVENTION (6)

25. **[IN PROMPT]** NO purple/blue AI gradient as default aesthetic — this is the #1 AI fingerprint on the planet. Neutral base + one considered accent only.

26. **[IN PROMPT]** NO pure `#000000` backgrounds. Use off-black: `#050505`, `#0a0a0a`, `zinc-950`, `slate-950`.

27. **[IN PROMPT]** ONE accent color per page. Every CTA, every highlight, every active state uses the exact same accent. Second accent color = design scatter.

28. **[MISSING — ADD]** Accent saturation: keep below 80%. Desaturate the accent so it blends with neutrals rather than screaming. Saturated accents = toy website.

29. **[MISSING — ADD]** Tint shadows to match background hue. A dark navy page gets dark navy shadows, not `rgba(0,0,0,0.3)`. Colored shadows read as premium; pure black shadows read as Bootstrap.

30. **[MISSING — ADD]** NO random dark section inserted into a light-mode page (or vice versa). A sudden `bg-slate-900` block in a cream-colored page looks like a copy-paste accident. Either commit to dark mode throughout or use a darker shade of the same palette for contrast sections.

---

## LAYOUT ANTI-PATTERNS (7)

31. **[IN PROMPT]** NEVER 3 equal-column equal-height feature cards. Replace with: 2-col zigzag, asymmetric bento, horizontal scroll gallery, or masonry. No exceptions.

32. **[IN PROMPT]** `min-height: 100dvh` everywhere full-viewport height is needed. NEVER `height: 100vh` — iOS Safari has a persistent viewport-jumping bug with `100vh`.

33. **[MISSING — ADD]** `<main className="overflow-x-hidden w-full max-w-full">` — wraps the entire page. Prevents horizontal scrollbars caused by off-screen GSAP starting positions and animated elements.

34. **[IN PROMPT]** Section padding minimum `py-24 md:py-32`. Sections must feel like distinct cinematic chapters. If you're using `py-16` or less, the layout feels cramped and unfinished.

35. **[MISSING — ADD]** Bento grids: `grid-flow-dense` (CSS `grid-auto-flow: dense`) on every grid. Mathematically verify `col-span` + `row-span` values fill the grid completely — no empty dead cells in corners.

36. **[IN PROMPT]** Floating pill nav: `mt-6 mx-auto w-max rounded-full backdrop-blur-xl` — detached from the top edge. NOT an edge-to-edge sticky navbar glued to the viewport top.

37. **[MISSING — ADD]** Mobile collapse (< 768px): ALL asymmetric layouts → `w-full px-4 py-8 grid-cols-1`. Remove all CSS rotations, negative-margin overlaps, and absolute positioning offsets. Overlapping elements on mobile cause broken touch targets.

---

## CARD & COMPONENT ARCHITECTURE (4)

38. **[IN PROMPT]** Double-Bezel on ALL major cards: outer wrapper `ring-1 ring-white/10 rounded-[2rem] p-1.5 bg-white/5` + inner content div with its own background and `shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)] rounded-[calc(2rem-0.375rem)]`. Concentric radii are mandatory.

39. **[MISSING — ADD]** Button-in-button trailing icon: arrow or icon beside CTA text is NEVER naked. It must be nested inside its own `w-8 h-8 rounded-full bg-white/10` circle placed flush with the button's right inner padding. This is the difference between a $50k design and a template.

40. **[IN PROMPT]** Primary CTAs: `rounded-full px-6 py-3`. Never sharp-cornered primary buttons on premium SMB demos.

41. **[IN PROMPT]** Hover state mandatory on every interactive element: minimum background color shift + `scale(1.02)`. An element with no hover response feels dead and unfinished to the prospect.

---

## ICONS & ASSETS (3)

42. **[IN PROMPT]** Phosphor icons ONLY — `@phosphor-icons/react` with `weight="light"` or `weight="regular"`, `size={20}`. Lucide, FontAwesome, and Material icons are banned (they have a specific "AI-built" fingerprint).

43. **[MISSING — ADD]** Picsum images: always use a descriptive seed matching the mood (`https://picsum.photos/seed/zahnarzt-berlin/1600/900`). Add CSS filters to avoid boring stock look: `filter: grayscale(15%) contrast(1.08)` or `mix-blend-mode: luminosity`. Never default Picsum without treatment.

44. **[MISSING — ADD]** Alt text on all meaningful images — `alt=""` on decorative images only. Never `alt="image"` or `alt="photo"` on anything that communicates content. This is also an SEO signal.

---

## CONTENT & COPY AI-TELLS (7)

45. **[IN PROMPT]** NO em-dashes (—) anywhere in output — not in copy, not in JSX comments, not in attributions. Use a hyphen (-) or a period. Zero tolerance.

46. **[IN PROMPT]** NO meta-labels: NEVER "SECTION 01", "CAPABILITY 03", "QUESTION 05", "ABOUT US 04". They look cheap and instantly signal template.

47. **[IN PROMPT]** NO AI copywriting clichés: "Elevate", "Seamless", "Unleash", "Next-Gen", "Game-changer", "Delve", "Tapestry", "In the world of...", "Revolutionize". Write plain, specific, confident German.

48. **[MISSING — ADD]** NO fake-precise round numbers: never `99.9%`, `€100.00`, `50 Kunden`. Use organic data: `47 Bewertungen`, `€89/Monat`, `+49 30 28474839`. Round numbers read as invented.

49. **[IN PROMPT]** NO Lorem ipsum anywhere. Real German draft copy from the business brief. Use actual service names, real district names, real business data. Invent nothing.

50. **[IN PROMPT]** NO hero stamps, floating badges on headings, pill-tags under H1, scroll-cue arrows (↓ Scroll), or version stamps (v2.1, BETA). The hero must be clean, spacious, typographically driven.

---

## SUMMARY: What's MISSING from `_BASE_PROMPT` (rules to add)

Rules **3, 4, 7, 10, 15, 17, 19, 20, 21, 22, 23, 24, 28, 29, 30, 33, 35, 37, 39, 43, 44, 48** are not in the current `_BASE_PROMPT`.

That's 22 rules missing. Adding them would measurably improve demo output without requiring any LLM architecture changes — just a better system prompt.
