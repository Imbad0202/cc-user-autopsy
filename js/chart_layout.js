// Pure layout helpers for canvas charts. No DOM/canvas API access — they
// take a `charWidth(label) -> px` measurement function so tests can supply
// a deterministic stub and runtime can pass `(s) => ctx.measureText(s).width`.
//
// Inlined into build_html.py output via a placeholder; also CommonJS-exported
// so node:test can load it directly.

const ROTATE_RAD = Math.PI / 4; // -45deg in browser, magnitude only here
const COS_SIN = Math.cos(ROTATE_RAD); // == sin, ~0.7071
const ELLIPSIS = '…';

function measureRotatedLabel(label, charWidth) {
  return charWidth(label) * COS_SIN;
}

function computeBarPlot({ width, height, legendBottom, labels, charWidth, yAxisMaxTickLabel }) {
  const longestRotated = labels.length
    ? Math.max(...labels.map((l) => measureRotatedLabel(l, charWidth)))
    : 0;
  // Vertical band must hold the rotated label projection plus a small gap.
  // Use ceil to avoid sub-pixel under-budgeting.
  const labelBand = Math.ceil(longestRotated + 12);
  // Left margin must hold the widest y-axis tick label plus 12px gap.
  const tickWidth = yAxisMaxTickLabel ? charWidth(yAxisMaxTickLabel) : 0;
  const left = Math.max(48, Math.ceil(tickWidth + 12));
  // Right margin must hold half of the rightmost rotated label so it
  // doesn't fall off the canvas. Bar centers sit at (i+0.5)*groupWidth
  // from plot.left, so the rightmost center extends `rotated/2` past it.
  const rightMargin = Math.ceil(longestRotated / 2 + 6);
  const top = legendBottom + 8;
  const plotWidth = Math.max(0, width - left - rightMargin);
  const plotHeight = Math.max(0, height - top - labelBand);
  return {
    left,
    top,
    width: plotWidth,
    height: plotHeight,
    labelBand,
    canvasWidth: width,
    canvasHeight: height,
  };
}

function clipLabelToWidth(label, maxWidth, charWidth) {
  if (!label) return '';
  if (charWidth(label) <= maxWidth) return label;
  const ellipsisWidth = charWidth(ELLIPSIS);
  if (ellipsisWidth > maxWidth) return '';
  let lo = 0;
  let hi = label.length;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (charWidth(label.slice(0, mid)) + ellipsisWidth <= maxWidth) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return lo > 0 ? label.slice(0, lo) + ELLIPSIS : '';
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { computeBarPlot, clipLabelToWidth, measureRotatedLabel };
}
