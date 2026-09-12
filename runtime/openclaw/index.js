import { execFileSync, spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { writeFileSync, renameSync } from 'node:fs';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const python = resolve(root, '.venv/bin/python');
export default {
  id: 'crop-forensics',
  name: 'Crop Forensics',
  register(api) {
    const streamPath = process.env.CROP_STREAM_PATH;
    const live = { state: 'running', run_id: process.env.CROP_RUN_ID, text: '', tools: [] };
    function publish() {
      if (!streamPath) return;
      writeFileSync(streamPath + '.plugin.tmp', JSON.stringify(live));
      renameSync(streamPath + '.plugin.tmp', streamPath);
    }
    // The documented runtime event bus emits public assistant text separately
    // from thinking. Subscribe only to assistant output, never reasoning events.
    api.runtime.events.onAgentEvent(event => {
      if (event.stream === 'assistant' && typeof event.data?.text === 'string') {
        live.text = event.data.text;
        publish();
      }
    });
    const schemas = JSON.parse(execFileSync(python, ['-m', 'runtime.bridge', 'schemas'], { cwd: root, encoding: 'utf8' }));
    for (const schema of schemas) {
      api.registerTool({
        name: schema.name, label: schema.name,
        description: schema.description, parameters: schema.input_schema,
        async execute(id, args) {
          live.tools.push({ id, name: schema.name, state: 'running' });
          publish();
          const result = await new Promise((resolveResult, reject) => {
            const child = spawn(python, ['-m', 'runtime.bridge'], { cwd: root, env: process.env, stdio: ['pipe', 'pipe', 'pipe'] });
            let output = '';
            const timer = setTimeout(() => { child.kill(); reject(new Error('Evidence tool timed out')); }, 30000);
            child.stdout.on('data', data => { output += data; });
            child.stderr.on('data', data => process.stderr.write(data));
            child.on('error', err => { clearTimeout(timer); reject(err); });
            child.on('close', code => {
              clearTimeout(timer);
              if (code !== 0) return reject(new Error('Evidence adapter failed; inspect local runtime logs.'));
              try { resolveResult(JSON.parse(output)); } catch (err) { reject(err); }
            });
            child.stdin.end(JSON.stringify({ name: schema.name, arguments: args, call_id: `${process.env.CROP_RUN_ID}:${id}` }));
          });
          Object.assign(live.tools.find(t => t.id === id), { state: result.ok ? 'complete' : 'failed', finding: result.data?.finding, error: result.error });
          publish();
          return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result, isError: !result.ok };
        }
      });
    }
  }
};
