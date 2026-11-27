import type {CSSProperties} from 'react';
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  staticFile,
} from 'remotion';
import type {CaptionLayer, GraphicLayer, OverlayPosition, RenderProps, TitleLayer} from './types';

export const secondsToFrames = (seconds: number, fps: number): number => Math.round(seconds * fps);

export const getTitleFrameRange = (
  title: TitleLayer,
  durationInFrames: number,
): {from: number; durationInFrames: number} => {
  const from = Math.max(0, Math.min(title.startFrame, durationInFrames));
  const remainingFrames = Math.max(0, durationInFrames - from);
  return {from, durationInFrames: Math.min(Math.max(0, title.durationInFrames), remainingFrames)};
};

export const sortCaptionsByStartFrame = (captions: readonly CaptionLayer[]): CaptionLayer[] =>
  captions
    .map((caption, index) => ({caption, index}))
    .sort((left, right) => left.caption.startFrame - right.caption.startFrame || left.index - right.index)
    .map(({caption}) => caption);

export const orderTitles = (titles: readonly TitleLayer[]): TitleLayer[] =>
  titles
    .map((title, index) => ({title, index}))
    .sort((left, right) => left.title.startFrame - right.title.startFrame || left.index - right.index)
    .map(({title}) => title);

const positionedLayerStyle = (position: OverlayPosition): CSSProperties => ({
  alignItems: 'center',
  display: 'flex',
  justifyContent: position === 'top' ? 'flex-start' : position === 'bottom' ? 'flex-end' : 'center',
  padding: '7%',
  pointerEvents: 'none',
});

const captionRange = (caption: CaptionLayer, durationInFrames: number) => {
  const from = Math.max(0, Math.min(caption.startFrame, durationInFrames));
  const end = Math.max(from, Math.min(caption.endFrame, durationInFrames));
  return {from, durationInFrames: end - from};
};

const graphicRange = (graphic: GraphicLayer, durationInFrames: number) => {
  const from = Math.max(0, Math.min(graphic.startFrame, durationInFrames));
  return {
    from,
    durationInFrames: Math.min(Math.max(0, graphic.durationInFrames), durationInFrames - from),
  };
};

export const AerialComposition: React.FC<RenderProps> = ({
  baseVideo,
  captions,
  durationInFrames,
  graphics,
  titles,
}) => {
  return (
    <AbsoluteFill>
      <OffthreadVideo src={staticFile(baseVideo)} />
      {orderTitles(titles).map((title, index) => {
        const range = getTitleFrameRange(title, durationInFrames);
        if (range.durationInFrames === 0) return null;
        return (
          <Sequence key={`title-${index}`} from={range.from} durationInFrames={range.durationInFrames}>
            <AbsoluteFill style={positionedLayerStyle(title.position)}>
              <span style={{backgroundColor: title.backgroundColor, color: title.color, fontSize: title.fontSize, padding: title.backgroundColor ? '0.2em 0.45em' : undefined}}>
                {title.text}
              </span>
            </AbsoluteFill>
          </Sequence>
        );
      })}
      {sortCaptionsByStartFrame(captions).map((caption, index) => {
        const range = captionRange(caption, durationInFrames);
        if (range.durationInFrames === 0) return null;
        return (
          <Sequence key={`caption-${index}`} from={range.from} durationInFrames={range.durationInFrames}>
            <AbsoluteFill style={positionedLayerStyle('bottom')}>
              <span style={{backgroundColor: 'rgba(0, 0, 0, 0.65)', color: '#fff', fontSize: 42, padding: '0.2em 0.45em'}}>{caption.text}</span>
            </AbsoluteFill>
          </Sequence>
        );
      })}
      {graphics.map((graphic, index) => {
        const range = graphicRange(graphic, durationInFrames);
        if (range.durationInFrames === 0) return null;
        return (
          <Sequence key={`graphic-${index}`} from={range.from} durationInFrames={range.durationInFrames}>
            <AbsoluteFill style={positionedLayerStyle(graphic.position)}>
              <img src={staticFile(graphic.asset)} style={{maxHeight: '100%', maxWidth: '100%', opacity: graphic.opacity, transform: `scale(${graphic.scale})`}} />
            </AbsoluteFill>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
