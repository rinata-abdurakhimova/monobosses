import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { format } from "prettier";

const source = new URL("../../../contracts/openapi.json", import.meta.url);
const output = new URL("../lib/contracts/generated.ts", import.meta.url);
const schemas = JSON.parse(await readFile(source, "utf8")).components.schemas;

function typeOf(schema) {
  if (schema.$ref) return schema.$ref.split("/").at(-1);
  if (schema.enum) return schema.enum.map(JSON.stringify).join(" | ");
  if (schema.const !== undefined) return JSON.stringify(schema.const);
  if (schema.anyOf) return schema.anyOf.map(typeOf).join(" | ");
  if (schema.type === "null") return "null";
  if (schema.type === "string") return "string";
  if (schema.type === "number" || schema.type === "integer") return "number";
  if (schema.type === "boolean") return "boolean";
  if (schema.type === "array") return `Array<${typeOf(schema.items ?? {})}>`;
  if (schema.properties) {
    const required = new Set(schema.required ?? []);
    return `{\n${Object.entries(schema.properties)
      .map(
        ([key, value]) =>
          `  ${JSON.stringify(key)}${required.has(key) ? "" : "?"}: ${typeOf(value)};`,
      )
      .join("\n")}\n}`;
  }
  if (schema.type === "object") {
    return `Record<string, ${
      typeof schema.additionalProperties === "object"
        ? typeOf(schema.additionalProperties)
        : "unknown"
    }>`;
  }
  return "unknown";
}

const rawContent =
  `// Generated from contracts/openapi.json. Run npm run contracts:generate.\n` +
  Object.entries(schemas)
    .map(([name, schema]) => `export type ${name} = ${typeOf(schema)};\n`)
    .join("\n");
const content = await format(rawContent, {
  parser: "typescript",
  printWidth: 80,
});

if (process.argv.includes("--check")) {
  if ((await readFile(output, "utf8")) !== content) {
    throw new Error(
      "Generated contract types are stale; run npm run contracts:generate.",
    );
  }
  console.log("Contract types match OpenAPI.");
} else {
  await writeFile(output, content);
  console.log(`Updated ${fileURLToPath(output)}`);
}
