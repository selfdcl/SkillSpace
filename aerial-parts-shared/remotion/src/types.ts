export type OverlayPosition = 'top' | 'center' | 'bottom';

export type TitleLayer = {
  text: string;
  startFrame: number;
  durationInFrames: number;
  position: OverlayPosition;
  fontSize: number;
  color: string;
  backgroundColor?: string;
};

export type CaptionLayer = {
  text: string;
  startFrame: number;
  endFrame: number;
};

export type GraphicLayer = {
  asset: string;
  startFrame: number;
  durationInFrames: number;
  position: OverlayPosition;
  scale: number;
  opacity: number;
};

export type RenderProps = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  baseVideo: string;
  titles: TitleLayer[];
  captions: CaptionLayer[];
  graphics: GraphicLayer[];
};
