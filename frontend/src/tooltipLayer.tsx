import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { placeTooltip, RectLike, TooltipPosition } from "./tooltip";

export type ActiveTooltip = {
  text: string;
  trigger: RectLike;
};

export function useGlobalTooltip() {
  const [tooltip, setTooltip] = useState<ActiveTooltip | null>(null);

  useEffect(() => {
    let activeTarget: HTMLElement | null = null;
    // This layer draws the title itself. Leaving the attribute in place makes
    // the browser draw the same text a second time after its own hover delay,
    // so the attribute is held here for as long as the tooltip is up.
    let suppressedTitle: string | null = null;

    const restoreTitle = () => {
      // A re-render may have written a fresh title while the old one was held;
      // that newer value wins.
      if (activeTarget && suppressedTitle !== null && !activeTarget.hasAttribute("title")) {
        activeTarget.setAttribute("title", suppressedTitle);
      }
      suppressedTitle = null;
    };

    const tooltipTarget = (target: EventTarget | null) => {
      if (!(target instanceof Element)) return null;
      const element = target.closest<HTMLElement>(".app-shell [title]");
      const text = element?.getAttribute("title")?.trim();
      return element && text ? { element, text } : null;
    };

    const showTooltip = (event: Event) => {
      const target = tooltipTarget(event.target);
      if (!target || target.element === activeTarget) return;
      restoreTitle();
      activeTarget = target.element;
      suppressedTitle = target.element.getAttribute("title");
      target.element.removeAttribute("title");
      setTooltip({ text: target.text, trigger: rectToPlainObject(target.element.getBoundingClientRect()) });
    };

    const hideTooltip = () => {
      restoreTitle();
      activeTarget = null;
      setTooltip(null);
    };

    const hideOnPointerOut = (event: PointerEvent) => {
      if (activeTarget && event.relatedTarget instanceof Node && activeTarget.contains(event.relatedTarget)) return;
      hideTooltip();
    };

    document.addEventListener("pointerover", showTooltip);
    document.addEventListener("focusin", showTooltip);
    document.addEventListener("pointerout", hideOnPointerOut);
    document.addEventListener("focusout", hideTooltip);
    window.addEventListener("scroll", hideTooltip, true);
    window.addEventListener("resize", hideTooltip);

    return () => {
      restoreTitle();
      document.removeEventListener("pointerover", showTooltip);
      document.removeEventListener("focusin", showTooltip);
      document.removeEventListener("pointerout", hideOnPointerOut);
      document.removeEventListener("focusout", hideTooltip);
      window.removeEventListener("scroll", hideTooltip, true);
      window.removeEventListener("resize", hideTooltip);
    };
  }, []);

  return tooltip;
}

export function TooltipLayer({ tooltip }: { tooltip: ActiveTooltip | null }) {
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<TooltipPosition | null>(null);

  useLayoutEffect(() => {
    setPosition(null);
  }, [tooltip]);

  useLayoutEffect(() => {
    if (!tooltip || !tooltipRef.current) return;
    const rect = tooltipRef.current.getBoundingClientRect();
    setPosition(placeTooltip(
      tooltip.trigger,
      { width: rect.width, height: rect.height },
      { width: window.innerWidth, height: window.innerHeight }
    ));
  }, [tooltip]);

  if (!tooltip) return null;

  return (
    <div
      ref={tooltipRef}
      className="ui-tooltip"
      role="tooltip"
      data-placement={position?.placement || "top"}
      style={position ? { left: position.left, top: position.top } : { left: 0, top: 0, visibility: "hidden" }}
    >
      {tooltip.text}
    </div>
  );
}

function rectToPlainObject(rect: DOMRect): RectLike {
  return {
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height
  };
}
