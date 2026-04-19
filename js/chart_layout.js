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

/**
 * Return the X position of the center of the i-th slot in a chart plot.
 * Used for both line-chart point X and x-axis label X so they always align.
 *
 * @param {number} index       - 0-based slot index
 * @param {number} labelCount  - total slot count (>=1)
 * @param {object} plot        - {left, width}
 * @returns {number}           - pixel X position, NaN if labelCount <= 0
 */
function slotCenterX(index, labelCount, plot) {
  if (labelCount <= 0) return NaN;
  const groupWidth = plot.width / labelCount;
  return plot.left + groupWidth * (index + 0.5);
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

/**
 * Split a list of points into contiguous runs of non-null points.
 * A point is "null" when its y is null or undefined or NaN.
 * Used by drawLinePath so line charts break (not dive to 0) on missing data.
 *
 * @param {Array<{x:number,y:number|null}>} points
 * @returns {Array<Array<{x:number,y:number}>>}  - array of runs; each run has >=1 points
 */
function segmentsWithoutNulls(points) {
  const runs = [];
  let current = [];
  for (const p of points) {
    const hasValue = p.y !== null && p.y !== undefined && !Number.isNaN(p.y);
    if (hasValue) {
      current.push(p);
    } else if (current.length) {
      runs.push(current);
      current = [];
    }
  }
  if (current.length) runs.push(current);
  return runs;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { computeBarPlot, clipLabelToWidth, measureRotatedLabel, slotCenterX, segmentsWithoutNulls };
}
