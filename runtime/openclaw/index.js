import { execFileSync, spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const python = resolve(root, '.venv/bin/python');
export default {
  id: 'crop-forensics',
  name: 'Crop Forensics',
  register(api) {
    const schemas = JSON.parse(execFileSync(python, ['-m', 'runtime.bridge', 'schemas'], { cwd: root, encoding: 'utf8' }));
    for (const schema of schemas) {
      api.registerTool({
        name: schema.name, label: schema.name,
        description: schema.description, parameters: schema.input_schema,
        async execute(id, args) {
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
          return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result, isError: !result.ok };
        }
      });
    }
  }
};
