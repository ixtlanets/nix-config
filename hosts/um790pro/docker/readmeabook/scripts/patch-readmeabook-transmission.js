#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const root = process.argv[2];
if (!root) {
  console.error("usage: patch-readmeabook-transmission.js <next-server-root>");
  process.exit(2);
}

const vulnerable = /mapStatus\(([$\w]+),([$\w]+)\)\{return \2>0\?"failed":/g;
const fixed = /mapStatus\(([$\w]+),([$\w]+)\)\{return \2===3\?"failed":/g;
let patchedCount = 0;
let alreadyPatchedCount = 0;
const requestLoggerMarker = 'RMABLogger.create("API.RequestById")';
const vulnerableRequestSerializer =
  /return ([$\w]+)\.NextResponse\.json\(\{success:!0,request:([$\w]+)\}\)/g;
const fixedRequestSerializer =
  /torrentSizeBytes:([$\w]+)\.torrentSizeBytes\?\.toString\(\)\?\?null/g;
let patchedRequestSerializerCount = 0;
let alreadyPatchedRequestSerializerCount = 0;

function visit(current) {
  for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
    const candidate = path.join(current, entry.name);
    if (entry.isDirectory()) {
      visit(candidate);
      continue;
    }
    if (!entry.isFile() || !entry.name.endsWith(".js")) {
      continue;
    }

    const source = fs.readFileSync(candidate, "utf8");
    const vulnerableMatches = [...source.matchAll(vulnerable)].length;
    const alreadyPatchedMatches = [...source.matchAll(fixed)].length;
    alreadyPatchedCount += alreadyPatchedMatches;

    let updated = source;
    if (vulnerableMatches > 0) {
      updated = updated.replace(
        vulnerable,
        (_match, statusName, errorName) =>
          `mapStatus(${statusName},${errorName}){return ${errorName}===3?"failed":`,
      );
      patchedCount += vulnerableMatches;
    }

    if (source.includes(requestLoggerMarker)) {
      const vulnerableSerializerMatches = [
        ...source.matchAll(vulnerableRequestSerializer),
      ].length;
      alreadyPatchedRequestSerializerCount += [
        ...source.matchAll(fixedRequestSerializer),
      ].length;
      if (vulnerableSerializerMatches > 0) {
        updated = updated.replace(
          vulnerableRequestSerializer,
          (_match, responseName, requestName) =>
            `return ${responseName}.NextResponse.json({success:!0,request:{...${requestName},downloadHistory:${requestName}.downloadHistory.map(e=>({...e,torrentSizeBytes:e.torrentSizeBytes?.toString()??null}))}})`,
        );
        patchedRequestSerializerCount += vulnerableSerializerMatches;
      }
    }

    if (updated !== source) {
      fs.writeFileSync(candidate, updated);
    }
  }
}

try {
  visit(root);
} catch (error) {
  console.error(`patch failed: ${error.message}`);
  process.exit(1);
}

if (patchedCount === 0 && alreadyPatchedCount === 0) {
  console.error("patch failed: no Transmission status mapper found");
  process.exit(1);
}
if (
  patchedRequestSerializerCount === 0 &&
  alreadyPatchedRequestSerializerCount === 0
) {
  console.error("patch failed: no request detail serializer found");
  process.exit(1);
}

if (patchedCount > 0) {
  console.log(`patched ${patchedCount} Transmission status mapper(s)`);
} else {
  console.log(`already patched ${alreadyPatchedCount} Transmission status mapper(s)`);
}
if (patchedRequestSerializerCount > 0) {
  console.log(`patched ${patchedRequestSerializerCount} request serializer(s)`);
} else {
  console.log(
    `already patched ${alreadyPatchedRequestSerializerCount} request serializer(s)`,
  );
}
