/**
 * Motion, kept to one idea.
 *
 * A single orchestrated entrance when the workspace first has data, and a
 * number that counts rather than snapping when the selected option changes.
 * Scattered hover effects and ambient loops are what make an interface feel
 * decorated; one well-timed sequence is what makes it feel finished.
 *
 * Everything here degrades to nothing under prefers-reduced-motion, and the
 * pre-animation state lives in CSS so nothing flashes before this runs.
 */

import { animate, stagger } from "animejs";

const REDUCED =
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Panels rise in reading order once the first case is on screen. */
export function revealWorkspace(): void {
  const panels = document.querySelectorAll<HTMLElement>(
    ".page-heading, .left-stack > *, .right-stack > *, .playback-row",
  );
  if (!panels.length) return;

  if (REDUCED) {
    panels.forEach((panel) => {
      panel.style.opacity = "1";
      panel.classList.remove("will-reveal");
    });
    return;
  }

  animate(panels, {
    opacity: [0, 1],
    translateY: [10, 0],
    duration: 620,
    delay: stagger(45),
    ease: "outQuart",
    onComplete: () => {
      panels.forEach((panel) => {
        panel.style.removeProperty("opacity");
        panel.style.removeProperty("transform");
        panel.classList.remove("will-reveal");
      });
    },
  });
}

/**
 * Count a readout to its new value.
 *
 * The figure still comes from the backend; this only animates the journey to
 * it, and lands exactly on the supplied number rather than near it.
 */
export function countTo(
  element: HTMLElement | null,
  value: number,
  format: (n: number) => string,
): void {
  if (!element) return;
  if (REDUCED) {
    element.textContent = format(value);
    return;
  }

  const from = Number(element.dataset.value ?? value);
  element.dataset.value = String(value);
  const state = { n: from };

  animate(state, {
    n: value,
    duration: 520,
    ease: "outExpo",
    onUpdate: () => {
      element.textContent = format(state.n);
    },
    onComplete: () => {
      element.textContent = format(value);
    },
  });
}

/** A short pulse on the element carrying a verdict that just changed. */
export function pulse(selector: string): void {
  if (REDUCED) return;
  const target = document.querySelector<HTMLElement>(selector);
  if (!target) return;
  animate(target, {
    scale: [1, 1.012, 1],
    duration: 420,
    ease: "outQuad",
  });
}
