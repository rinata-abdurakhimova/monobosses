import openapi from "../../../../contracts/openapi.json" with { type: "json" };

type Schema = {
  $ref?: string;
  type?: string;
  enum?: unknown[];
  const?: unknown;
  anyOf?: Schema[];
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: boolean | Schema;
  items?: Schema;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  minimum?: number;
  minItems?: number;
  maxItems?: number;
};

const schemas = openapi.components.schemas as Record<string, Schema>;

type ValidationOptions = {
  /** Display future expert IDs without weakening any other report fields. */
  allowUnknownRoles?: boolean;
};

/** Validate the shared OpenAPI schemas used at the frontend data boundary. */
export function validateContract(
  name: string,
  value: unknown,
  options: ValidationOptions = {},
): void {
  const schema = schemas[name];
  if (!schema) throw new Error(`Unknown contract schema: ${name}`);
  visit(schema, value, name, options);
}

function visit(
  schema: Schema,
  value: unknown,
  path: string,
  options: ValidationOptions,
): void {
  function invalid(): never {
    throw new Error(`${path} does not match the shared contract`);
  }
  if (schema.$ref) {
    const name = schema.$ref.split("/").at(-1)!;
    const target = schemas[name];
    if (!target) invalid();
    if (name === "RoleId" && options.allowUnknownRoles) {
      if (typeof value !== "string" || !/^[a-z][a-z0-9_]{0,127}$/.test(value))
        invalid();
      return;
    }
    return visit(target, value, path, options);
  }
  if (schema.anyOf) {
    for (const option of schema.anyOf) {
      try {
        visit(option, value, path, options);
        return;
      } catch {
        /* Try the next schema alternative. */
      }
    }
    invalid();
  }
  if (schema.enum && !schema.enum.includes(value)) invalid();
  if ("const" in schema && schema.const !== value) invalid();
  if (schema.type === "null" && value !== null) invalid();
  if (schema.type === "string") {
    if (typeof value !== "string") invalid();
    if (schema.minLength !== undefined && value.length < schema.minLength)
      invalid();
    if (schema.maxLength !== undefined && value.length > schema.maxLength)
      invalid();
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) invalid();
  }
  if (schema.type === "boolean" && typeof value !== "boolean") invalid();
  if (schema.type === "number" || schema.type === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value)) invalid();
    if (schema.type === "integer" && !Number.isInteger(value)) invalid();
    if (schema.minimum !== undefined && value < schema.minimum) invalid();
  }
  if (schema.type === "array") {
    if (!Array.isArray(value)) invalid();
    if (schema.minItems !== undefined && value.length < schema.minItems)
      invalid();
    if (schema.maxItems !== undefined && value.length > schema.maxItems)
      invalid();
    value.forEach((item, index) =>
      visit(schema.items ?? {}, item, `${path}[${index}]`, options),
    );
  }
  if (schema.type === "object") {
    if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
    const object = value as Record<string, unknown>;
    for (const key of schema.required ?? []) {
      if (!(key in object)) throw new Error(`${path}.${key} is required`);
    }
    for (const [key, item] of Object.entries(object)) {
      const property = schema.properties?.[key];
      if (property) visit(property, item, `${path}.${key}`, options);
      else if (schema.additionalProperties === false) invalid();
      else if (typeof schema.additionalProperties === "object") {
        visit(schema.additionalProperties, item, `${path}.${key}`, options);
      }
    }
  }
}
