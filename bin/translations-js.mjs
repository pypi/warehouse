#!/usr/bin/env node

/*
  based on:
  - po2json wrapper for gettext.js https://github.com/mikeedwards/po2json
  - based on https://github.com/guillaumepotier/gettext.js/blob/v2.0.2/bin/po2json

  Dump all .po files in one json file containing an array with entries like this one:

  {
    "": {
        "language": "en",
        "plural-forms": "nplurals=2; plural=(n!=1);"
    },
    "simple key": "It's tranlation",
    "another with %1 parameter": "It's %1 tranlsation",
    "a key with plural": [
        "a plural form",
        "another plural form",
        "could have up to 6 forms with some languages"
    ],
    "a context\u0004a contextualized key": "translation here"
  }

*/


import {readdir, readFile, stat, writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {po} from "gettext-parser";


const argv = process.argv;

const runPo2Json = async function (filePath) {
  const buffer = await readFile(filePath);
  const jsonData = po.parse(buffer, {defaultCharset:"utf-8", validation: false });

  // Build the format expected by gettext.js.
  // Includes only translations from .js files.
  // NOTE: This assumes there is only one msgctxt (the default ""),
  // and that default msgid ("") contains the headers.
  const translations = jsonData.translations[""];
  const jsonResult = {
    "": {
      "language": jsonData["headers"]["language"],
      "plural-forms": jsonData["headers"]["plural-forms"],
    }
  };

  for (const msgid in translations) {
    if ("" === msgid) {
      continue;
    }

    const item = translations[msgid];

    if (!item["comments"]["reference"].includes(".js:")) {
      // ignore non-js translations
      continue;
    }

    const values = item["msgstr"];
    if (!values.some((value) => value.length > 0 && value !== msgid)) {
      // only include if there are any translated strings
      continue;
    }

    if (item["msgstr"].length === 1) {
      jsonResult[msgid] = values[0];
    } else {
      jsonResult[msgid] = values;
    }
  }

  return jsonResult;
}


const recurseDir = async function recurseDir(dir) {
  const result = [];
  const files = await readdir(dir);
  for (const file of files) {
    const filePath = resolve(dir, file);
    const fileStat = await stat(filePath);
    if (fileStat.isDirectory()) {
      const results = await recurseDir(filePath);
      result.push(...results);
    } else if (filePath.endsWith("messages.po")) {
      const item = await runPo2Json(filePath);
      if (Object.keys(item).length > 1) {
        // only include if there are translated strings
        console.log(`found js messages in ${filePath}`);
        result.push(await runPo2Json(filePath));
      }
    }
  }
  return result;
};

const updateJsonTranslations = async function updateJsonTranslations(dir) {
  const result = await recurseDir(dir);
  const destFile = resolve("./warehouse/static/js/warehouse/utils/messages.json");
  const destData = JSON.stringify(result, null, 2)
  await writeFile(destFile, destData);
  console.log(`writing js messages to ${destFile}`);
}


updateJsonTranslations(argv[2]);
