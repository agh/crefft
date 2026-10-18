export function contrastRatio(foreground, background) {
  const luminance = (hex) => {
    const rgb = hex.slice(1).match(/../g).map((channel) => parseInt(channel, 16) / 255)
      .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  };
  const a = luminance(foreground);
  const b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

export function contrastPairs(palettes) {
  return Object.entries(palettes).flatMap(([mode, colors]) => {
    const pairs = ['canvas', 'surface'].flatMap((background) =>
      ['ink', 'secondary', 'accent', 'accentHover', 'good', 'bad', 'edge', 'focus'].map((foreground) => ({
        foreground, background, minimum: ['edge', 'focus'].includes(foreground) ? 3 : 4.5,
      })));
    pairs.push(...['accent', 'accentHover'].map((background) => ({
      foreground: 'canvas', background, minimum: 4.5,
    })));
    return pairs.map((pair) => ({
      mode, ...pair, ratio: contrastRatio(colors[pair.foreground], colors[pair.background]),
    }));
  });
}
