/* SPDX-License-Identifier: Apache-2.0 */

// The value for 'messagesAccessLocaleData' is replaced by webpack.plugin.localize.js.
// The variable name must match the name used in webpack.plugin.localize.js.
// Default is 'en'.
const messagesAccessLocaleData = {"": {"language": "en", "plural-forms": "nplurals = 2; plural = (n != 1)"}};

// The value for 'messagesAccessPluralFormFunction' is replaced by webpack.plugin.localize.js.
// The variable name must match the name used in webpack.plugin.localize.js.
// Default is 'en'.
const messagesAccessPluralFormFunction = function (n) {
  let nplurals, plural;
  nplurals = 2; plural = (n != 1);
  return {total: nplurals, index: ((nplurals > 1 && plural === true) ? 1 : (plural ? plural : 0))};
};

/**
 * Get the translation using num to choose the appropriate string.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 * Function 'ngettext' for plural extraction.
 *
 * Any placeholders must be specified as %1, %2, etc.
 *
 * @example
 * import { ngettext } from "warehouse/utils/messages-access";
 * // For a singular and plural and placeholder string:
 * ngettext("About a minute ago", "About %1 minutes ago", numMinutes, numMinutes);

 * @param singular {string} The default string for the singular translation.
 * @param plural {string|null} The default string for the plural translation.
 * @param num {number} The number to use to select the appropriate translation.
 * @param extras {string} Additional values to put in placeholders.
 * @returns {string} The translated text.
 * @see https://github.com/guillaumepotier/gettext.js
 * @see https://www.gnu.org/software/gettext/manual/gettext.html#Language-specific-options
 * @see https://docs.pylonsproject.org/projects/pyramid/en/latest/api/i18n.html#pyramid.i18n.Localizer.pluralize
 */
export function ngettext(singular, plural, num, ...extras) {
  return ngettextCustom(singular, plural, num, extras, messagesAccessLocaleData, messagesAccessPluralFormFunction);
}

/**
 * Get the singular translation.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 * Function 'gettext' for singular extraction.
 *
 * Any placeholders must be specified as %1, %2, etc.
 *
 * @example
 * import { gettext } from "warehouse/utils/messages-access";
 * // For a singular only string:
 * gettext("Just now");
 *
 * @param singular {string} The default string for the singular translation.
 * @param extras {string} Additional values to put in placeholders.
 * @returns {string} The translated text.
 */
export function gettext(singular, ...extras) {
  return ngettextCustom(singular, null, 1, extras, messagesAccessLocaleData, messagesAccessPluralFormFunction);
}

/**
 * Check whether the current locale has a translation for a string.
 * @param singular {string} The default string for the singular translation, used as the key.
 * @returns {boolean}
 */
export function hasTranslation(singular) {
  return hasTranslationCustom(singular, messagesAccessLocaleData);
}

/**
 * Check whether the locale data has a translation for a string.
 * @param singular {string} The default string for the singular translation, used as the key.
 * @param data {{}} The locale data used for translation.
 * @returns {boolean}
 */
export function hasTranslationCustom(singular, data) {
  if (!singular) {
    return false;
  }
  const language = data?.[""]?.["language"];
  if (!language) {
    return false;
  }
  if (language === "en") {
    return true;
  }
  if (!Object.hasOwn(data, singular)) {
    return false;
  }
  let value = data[singular];
  if (!Array.isArray(value)) {
    value = [value];
  }
  return value.length > 0 && value.every((str) => str !== "");
}

/**
 * Get the translation.
 * @param singular {string} The default string for the singular translation.
 * @param plural {string|null} The default string for the plural translation.
 * @param num {number} The number to use to select the appropriate translation.
 * @param extras {string[]} Additional values to put in placeholders.
 * @param data {{}} The locale data used for translation.
 * @param pluralForms The function that calculates the plural form.
 * @returns {string} The translated text.
 */
export function ngettextCustom(singular, plural, num, extras, data, pluralForms) {
  // This function allows for testing and
  // allows ngettext and gettext to have the signatures required by pybabel.
  let value = getTranslationData(data, singular);
  if (Array.isArray(value)) {
    value = value[pluralForms(num).index];
  } else if (plural !== null && !Object.hasOwn(data, singular) && num !== 1) {
    value = plural;
  }
  return insertPlaceholderValues(value, extras);
}

/**
 * Get translation data safely.
 * @param data {{}} The locale data used for translation.
 * @param value {string} The default string for the singular translation, used as the key.
 * @returns {string|string[]}
 */
function getTranslationData(data, value) {
  if (!value || !value.trim()) {
    return "";
  }
  if (Object.hasOwn(data, value)) {
    return data[value];
  } else {
    return value;
  }
}

/**
 * Insert placeholder values into a string.
 * @param value {string} The translated string that might have placeholder values.
 * @param extras {string[]} Additional values to put in placeholders.
 * @returns {string}
 */
function insertPlaceholderValues(value, extras) {
  if (!value) {
    return "";
  }
  if (!extras || extras.length < 1 || !value.includes("%")) {
    return value;
  }
  return extras.reduce((accumulator, currentValue, currentIndex) => {
    const regexp = new RegExp(`%${currentIndex + 1}\\b`, "gi");
    return accumulator.replaceAll(regexp, currentValue);
  }, value);
}
