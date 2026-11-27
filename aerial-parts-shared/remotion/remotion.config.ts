import {Config} from '@remotion/cli/config';

const licenseKey = process.env.REMOTION_LICENSE_KEY?.trim();

if (!licenseKey) {
  throw new Error(
    'REMOTION_LICENSE_KEY must be explicitly set before rendering. Eligible users may explicitly set it to free-license.',
  );
}

Config.setPublicLicenseKey(licenseKey);
