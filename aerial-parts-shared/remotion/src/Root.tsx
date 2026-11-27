import {Composition} from 'remotion';
import {AerialComposition} from './AerialComposition';
import type {RenderProps} from './types';

const defaultProps: RenderProps = {
  fps: 30,
  width: 1920,
  height: 1080,
  durationInFrames: 1,
  baseVideo: 'base.mp4',
  titles: [],
  captions: [],
  graphics: [],
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="AerialPackage"
    component={AerialComposition}
    defaultProps={defaultProps}
    durationInFrames={defaultProps.durationInFrames}
    fps={defaultProps.fps}
    width={defaultProps.width}
    height={defaultProps.height}
    calculateMetadata={({props}) => ({
      durationInFrames: props.durationInFrames,
      fps: props.fps,
      height: props.height,
      width: props.width,
    })}
  />
);
