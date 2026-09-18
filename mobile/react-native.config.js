/**
 * Config do React Native CLI — autolinking.
 *
 * O template RN 0.76 removeu o atributo `package` do AndroidManifest
 * (namespace vive no build.gradle), e a detecção automática do
 * packageName falha neste ambiente — declaramos explicitamente.
 */
module.exports = {
  project: {
    android: {
      sourceDir: "android",
      packageName: "com.gasflowdriver",
    },
  },
};
