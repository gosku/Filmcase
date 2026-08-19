/**
 * The browser-side layering contract.
 *
 * The JavaScript counterpart to the import-linter contract in setup.cfg. That
 * one cannot see this code, and the layering is easier to break here: an import
 * is one line and nothing in the language objects.
 *
 * The direction is interfaces -> application -> domain -> vendor. There is no
 * data layer, because the client owns no database. What it has instead is a
 * vendor layer, for everything that talks to something outside the browser:
 * the Filmcase backend, and the camera.
 *
 * That is why ptp_usb_device.js sits in vendor rather than domain, where its
 * Python counterpart lives. It speaks a foreign protocol to a foreign system.
 * The device contract that the domain depends on is the typedef beside it; the
 * transport behind that contract is not domain logic in either codebase, and
 * the Python placement is worth revisiting on its own terms.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const CAMERA_ROOT = fileURLToPath(
  new URL("../../src/interfaces/static/js/camera", import.meta.url)
);

/** Outermost first. A module may import its own layer or any layer below. */
const LAYERS = ["interfaces", "application", "domain", "vendor"];

function jsFilesIn(directory) {
  const found = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      found.push(...jsFilesIn(path));
    } else if (entry.endsWith(".js")) {
      found.push(path);
    }
  }
  return found;
}

/** The layer a file belongs to, from the first path segment under camera/. */
function layerOf(path) {
  const [segment] = relative(CAMERA_ROOT, path).split("/");
  return LAYERS.indexOf(segment);
}

/** Every relative import specifier in a module. */
function importsOf(path) {
  const source = readFileSync(path, "utf8");
  const specifiers = [];
  const pattern = /^\s*import\s+[^;]*?from\s+["']([^"']+)["']/gm;
  let match;
  while ((match = pattern.exec(source)) !== null) {
    specifiers.push(match[1]);
  }
  return specifiers;
}

const MODULES = jsFilesIn(CAMERA_ROOT);

describe("the browser-side layering contract", () => {
  it("finds the modules to check", () => {
    // A test that silently checks nothing is worse than no test.
    assert.ok(MODULES.length >= 8, `only found ${MODULES.length} modules`);
  });

  it("puts every module in a known layer", () => {
    // A module at the camera root belongs to no layer, so nothing constrains
    // what it may import or who may import it.
    const strays = MODULES.filter((path) => layerOf(path) === -1).map((path) =>
      relative(CAMERA_ROOT, path)
    );

    assert.deepEqual(strays, []);
  });

  it("has at least one module in each layer that is in use", () => {
    // interfaces is absent until the button wiring lands, and this list grows
    // to include it then. Everything below it exists now, and a layer quietly
    // emptying is worth failing over: the per-module checks would simply have
    // fewer entries and say nothing.
    const populated = new Set(MODULES.map((path) => LAYERS[layerOf(path)]));

    for (const layer of ["application", "domain", "vendor"]) {
      assert.ok(populated.has(layer), `nothing in the ${layer} layer`);
    }
  });

  for (const path of MODULES) {
    const name = relative(CAMERA_ROOT, path);

    it(`${name} imports only its own layer or below`, () => {
      const from = layerOf(path);

      for (const specifier of importsOf(path)) {
        if (!specifier.startsWith(".")) {
          // A bare specifier would be a package, and the browser code has no
          // dependencies by design.
          assert.fail(`${name} imports the package ${specifier}`);
        }
        const target = resolve(dirname(path), specifier);
        const to = layerOf(target);
        assert.notEqual(to, -1, `${name} imports outside any layer: ${specifier}`);
        assert.ok(
          to >= from,
          `${name} (${LAYERS[from]}) imports ${specifier} (${LAYERS[to]}), ` +
            "which is outward. Dependencies flow inward only."
        );
      }
    });
  }

  it("keeps the domain layer off the transport", () => {
    // The domain may use the device contract, but constructing a transport or
    // touching navigator.usb from there would put WebUSB behind a function
    // whose job is arithmetic on recipe values.
    const domainModules = MODULES.filter((path) => LAYERS[layerOf(path)] === "domain");
    assert.ok(domainModules.length > 0);

    for (const path of domainModules) {
      const source = readFileSync(path, "utf8");
      const name = relative(CAMERA_ROOT, path);
      assert.ok(!source.includes("navigator.usb"), `${name} reaches for navigator.usb`);
      assert.ok(
        !source.includes("new ClientPTPUSBDevice"),
        `${name} constructs a transport`
      );
    }
  });

  it("keeps fetch out of everything but the vendor layer", () => {
    // Talking to the backend is a vendor concern. A domain function that
    // fetched would be untestable without a network stub and would make a
    // conversion depend on the server being up.
    for (const path of MODULES) {
      if (LAYERS[layerOf(path)] === "vendor") continue;
      const source = readFileSync(path, "utf8");
      assert.ok(
        !/\bfetch\s*\(/.test(source),
        `${relative(CAMERA_ROOT, path)} calls fetch outside the vendor layer`
      );
    }
  });
});
