/** Whether this browser can run MapLibre, which needs WebGL 2. */
export function supportsWebGL2(): boolean {
  const gl = document.createElement('canvas').getContext('webgl2')
  gl?.getExtension('WEBGL_lose_context')?.loseContext() // free the test context right away
  return gl !== null
}
