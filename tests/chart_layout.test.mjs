import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const layout = require(path.join(here, '..', 'js', 'chart_layout.js'));

const { computeBarPlot, clipLabelToWidth, measureRotatedLabel } = layout;

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
