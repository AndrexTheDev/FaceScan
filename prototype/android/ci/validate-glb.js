const fs = require('fs');
const validator = require(process.env.RUNNER_TEMP + '/facescan-validator/node_modules/gltf-validator');
(async () => {
  for (const name of ['facescan-synthetic.glb', 'facescan-synthetic-textured.glb']) {
    const file = process.env.RUNNER_TEMP + '/' + name;
    const result = await validator.validateBytes(new Uint8Array(fs.readFileSync(file)), { uri: name });
    for (const message of result.issues.messages) {
      const level = message.severity === 0 ? 'error' : 'notice';
      console.log(`::${level} title=glTF-Validator::${name}: ${message.code}: ${message.message}`);
    }
    console.log(`::notice title=glTF-Validator::${name}: ${result.issues.numErrors} Fehler, ${result.issues.numWarnings} Warnungen`);
    if (result.issues.numErrors) process.exitCode = 1;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
