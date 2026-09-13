import { spawnSync } from 'node:child_process'
import { readdirSync } from 'node:fs'
import { resolve } from 'node:path'

const testDirectory = resolve('.test-dist', 'tests')
const testFiles = readdirSync(testDirectory, { withFileTypes: true })
  .filter((entry) => entry.isFile() && entry.name.endsWith('.test.js'))
  .map((entry) => resolve(testDirectory, entry.name))
  .sort()

if (testFiles.length === 0) {
  throw new Error(`No compiled tests found in ${testDirectory}`)
}

const result = spawnSync(process.execPath, ['--test', ...testFiles], {
  stdio: 'inherit',
})

if (result.error) {
  throw result.error
}

process.exit(result.status ?? 1)
