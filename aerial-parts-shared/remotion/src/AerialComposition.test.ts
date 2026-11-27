import {describe, expect, it} from 'vitest';
import {
  getTitleFrameRange,
  orderTitles,
  secondsToFrames,
  sortCaptionsByStartFrame,
} from './AerialComposition';
import type {CaptionLayer, TitleLayer} from './types';

describe('AerialComposition timing helpers', () => {
  it('converts seconds to deterministic frame counts', () => {
    expect(secondsToFrames(3.8, 30)).toBe(114);
  });

  it('clips title frame ranges to the base-video duration', () => {
    const title: TitleLayer = {
      text: 'Coast',
      startFrame: 110,
      durationInFrames: 30,
      position: 'bottom',
      fontSize: 64,
      color: '#ffffff',
    };

    expect(getTitleFrameRange(title, 120)).toEqual({from: 110, durationInFrames: 10});
  });

  it('sorts caption cues by explicit start frame', () => {
    const captions: CaptionLayer[] = [
      {text: 'Second', startFrame: 30, endFrame: 45},
      {text: 'First', startFrame: 5, endFrame: 20},
    ];

    expect(sortCaptionsByStartFrame(captions).map((caption) => caption.text)).toEqual([
      'First',
      'Second',
    ]);
  });

  it('uses source order as a deterministic tie breaker for overlapping titles', () => {
    const titles: TitleLayer[] = [
      {text: 'First', startFrame: 10, durationInFrames: 20, position: 'top', fontSize: 48, color: '#fff'},
      {text: 'Second', startFrame: 10, durationInFrames: 20, position: 'bottom', fontSize: 48, color: '#fff'},
    ];

    expect(orderTitles(titles).map((title) => title.text)).toEqual(['First', 'Second']);
  });
});
