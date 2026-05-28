export type RectLike = {
  left: number;
  top: number;
  width: number;
  height: number;
};

export type SizeLike = {
  width: number;
  height: number;
};

export type TooltipPlacement = "top" | "bottom";

export type TooltipPosition = {
  left: number;
  top: number;
  placement: TooltipPlacement;
};

export function placeTooltip(
  trigger: RectLike,
  tooltip: SizeLike,
  viewport: SizeLike,
  margin = 8,
  gap = 8
): TooltipPosition {
  const maxLeft = Math.max(margin, viewport.width - tooltip.width - margin);
  const centeredLeft = trigger.left + trigger.width / 2 - tooltip.width / 2;
  const left = clamp(centeredLeft, margin, maxLeft);

  const preferredTop = trigger.top - tooltip.height - gap;
  if (preferredTop >= margin) {
    return {
      left,
      top: clamp(preferredTop, margin, Math.max(margin, viewport.height - tooltip.height - margin)),
      placement: "top"
    };
  }

  return {
    left,
    top: clamp(trigger.top + trigger.height + gap, margin, Math.max(margin, viewport.height - tooltip.height - margin)),
    placement: "bottom"
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
