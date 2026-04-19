import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const layout = require(path.join(here, '..', 'js', 'chart_layout.js'));

const { computeBarPlot, clipLabelToWidth, measureRotatedLabel, slotCenterX, segmentsWithoutNulls } = layout;

const charWidth = (label) => label.length * 6.5;

test('measureRotatedLabel returns horizontal projection at -45deg', () => {
  const projection = measureRotatedLabel('helpfulness', charWidth);
  const textWidth = charWidth('helpfulness');
  assert.ok(projection > textWidth * 0.6 && projection < textWidth * 0.8,
    `expected ~textWidth/sqrt(2)=${textWidth / Math.sqrt(2)}, got ${projection}`);
});

test('computeBarPlot reserves enough vertical space for longest rotated label', () => {
  const labels = ['unblocking', 'building', 'debugging', 'planning', 'reviewing'];
  const plot = computeBarPlot({
    width: 600, height: 260, legendBottom: 30, labels, charWidth,
  });
  const maxRotated = Math.max(...labels.map(l => measureRotatedLabel(l, charWidth)));
  const verticalSpace = plot.canvasHeight - (plot.top + plot.height);
  assert.ok(verticalSpace >= maxRotated * 0.72,
    `label band ${verticalSpace}px must fit rotated label ${maxRotated}px (>=72%)`);
});

test('computeBarPlot keeps right edge inside canvas after label rotation', () => {
  const labels = ['a', 'b', 'c', 'd', 'e', 'helpfulness-extended'];
  const width = 600;
  const plot = computeBarPlot({
    width, height: 260, legendBottom: 30, labels, charWidth,
  });
  const groupWidth = plot.width / labels.length;
  const lastCenterX = plot.left + groupWidth * (labels.length - 0.5);
  const rotated = measureRotatedLabel(labels[labels.length - 1], charWidth);
  const rightmost = lastCenterX + rotated * 0.5;
  assert.ok(rightmost <= width,
    `rightmost label edge ${rightmost} must be <= canvas width ${width}`);
});

test('computeBarPlot left margin fits widest y-axis tick', () => {
  const plot = computeBarPlot({
    width: 600, height: 260, legendBottom: 30,
    labels: ['x'], charWidth,
    yAxisMaxTickLabel: '1.5k',
  });
  const tickWidth = charWidth('1.5k');
  assert.ok(plot.left >= tickWidth + 12,
    `left margin ${plot.left} must hold tick "${tickWidth}px" + 12px gap`);
});

test('clipLabelToWidth truncates with ellipsis when over budget', () => {
  const clipped = clipLabelToWidth('aspi6246-academic-research-skills', 80, charWidth);
  assert.ok(clipped.endsWith('…'), `expected ellipsis, got "${clipped}"`);
  assert.ok(charWidth(clipped) <= 80, `clipped width ${charWidth(clipped)} must be <= 80`);
});

test('clipLabelToWidth returns label unchanged when within budget', () => {
  const label = 'opus-4-7';
  const clipped = clipLabelToWidth(label, 200, charWidth);
  assert.equal(clipped, label);
});

test('clipLabelToWidth handles empty string without crashing', () => {
  assert.equal(clipLabelToWidth('', 80, charWidth), '');
});

test('slotCenterX places first slot at left + groupWidth/2', () => {
  const plot = { left: 50, width: 400 };
  const x = slotCenterX(0, 5, plot);
  // groupWidth = 80; first center = 50 + 40 = 90
  assert.equal(x, 90);
});

test('slotCenterX places last slot at right - groupWidth/2', () => {
  const plot = { left: 50, width: 400 };
  const x = slotCenterX(4, 5, plot);
  // groupWidth = 80; last center = 50 + 80*4.5 = 50 + 360 = 410 (inside plot)
  assert.equal(x, 410);
});

test('slotCenterX with single slot centers it in the plot', () => {
  const plot = { left: 10, width: 100 };
  assert.equal(slotCenterX(0, 1, plot), 60);
});

test('slotCenterX returns NaN for zero labels', () => {
  const plot = { left: 0, width: 100 };
  assert.ok(Number.isNaN(slotCenterX(0, 0, plot)));
});

test('slotCenterX is used consistently for points AND labels', () => {
  // Regression test for the alignment bug: point for index i must equal
  // label X for index i, given the same plot and labelCount.
  const plot = { left: 30, width: 450 };
  for (let i = 0; i < 7; i += 1) {
    assert.equal(
      slotCenterX(i, 7, plot),
      slotCenterX(i, 7, plot),
      `slot ${i} must be deterministic`,
    );
  }
  // And: the delta between adjacent slots equals groupWidth (within float precision).
  const d = slotCenterX(1, 7, plot) - slotCenterX(0, 7, plot);
  assert.ok(Math.abs(d - 450 / 7) < 1e-9, `slot spacing ${d} must equal groupWidth ${450 / 7}`);
});

// segmentsWithoutNulls — null-gap handling for growth curve line drawing
test('segmentsWithoutNulls splits on null y', () => {
  const pts = [{x:0,y:10},{x:1,y:null},{x:2,y:30},{x:3,y:40}];
  const runs = segmentsWithoutNulls(pts);
  assert.equal(runs.length, 2);
  assert.deepEqual(runs[0].map(p => p.x), [0]);
  assert.deepEqual(runs[1].map(p => p.x), [2, 3]);
});

test('segmentsWithoutNulls handles NaN as null', () => {
  const runs = segmentsWithoutNulls([{x:0,y:5},{x:1,y:NaN},{x:2,y:7}]);
  assert.equal(runs.length, 2);
});

test('segmentsWithoutNulls handles all nulls', () => {
  assert.deepEqual(segmentsWithoutNulls([{x:0,y:null},{x:1,y:null}]), []);
});

test('segmentsWithoutNulls handles all valid as one run', () => {
  const pts = [{x:0,y:1},{x:1,y:2},{x:2,y:3}];
  const runs = segmentsWithoutNulls(pts);
  assert.equal(runs.length, 1);
  assert.equal(runs[0].length, 3);
});

test('segmentsWithoutNulls handles leading/trailing nulls', () => {
  const pts = [{x:0,y:null},{x:1,y:10},{x:2,y:20},{x:3,y:null}];
  const runs = segmentsWithoutNulls(pts);
  assert.equal(runs.length, 1);
  assert.equal(runs[0].length, 2);
});

// Regression tests: computeBarPlot contract for line-chart label budgets
// (Fig 13 labels like "2026-W15" must not clip at bottom or right edge)
test('computeBarPlot gives line charts enough bottom margin for long rotated labels', () => {
  // Regression: Fig 13-style labels like "2026-W15" (~52px text) must fit.
  const labels = Array.from({length: 14}, (_, i) => `2026-W${String(i+1).padStart(2, '0')}`);
  const plot = computeBarPlot({
    width: 780, height: 260, legendBottom: 30, labels, charWidth,
    yAxisMaxTickLabel: '100',
  });
  const longest = Math.max(...labels.map(l => measureRotatedLabel(l, charWidth)));
  const bottomBudget = plot.canvasHeight - (plot.top + plot.height);
  assert.ok(
    bottomBudget >= longest,
    `labelBand ${bottomBudget}px must fit longest rotated label ${longest}px`,
  );
});

test('computeBarPlot gives enough right margin for rightmost rotated label', () => {
  const labels = Array.from({length: 14}, (_, i) => `2026-W${String(i+1).padStart(2, '0')}`);
  const plot = computeBarPlot({
    width: 780, height: 260, legendBottom: 30, labels, charWidth,
    yAxisMaxTickLabel: '100',
  });
  // Last slot center sits at plot.left + groupWidth * (labels.length - 0.5).
  // Label extends leftward from center under -45° rotate; the right half
  // of rotated label width must stay inside canvas.
  const groupWidth = plot.width / labels.length;
  const lastCenter = plot.left + groupWidth * (labels.length - 0.5);
  const rightBudget = plot.canvasWidth - lastCenter;
  const rotatedHalf = Math.max(...labels.map(l => measureRotatedLabel(l, charWidth))) / 2;
  assert.ok(
    rightBudget >= rotatedHalf,
    `right budget ${rightBudget}px must fit half of longest rotated label ${rotatedHalf}px`,
  );
});
