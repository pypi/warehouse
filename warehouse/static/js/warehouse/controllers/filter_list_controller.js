/* SPDX-License-Identifier: Apache-2.0 */

import {Controller} from "@hotwired/stimulus";
import {gettext, ngettext} from "../utils/messages-access";

/**
 * A Stimulus controller for filtering a list of items, using input and select elements.
 *
 * Each element can filter on one data attribute applied to items in the list to be filtered.
 *
 * Add these data attributes to each input / select:
 * - data-action="filter-list#filter"
 * - data-filter-list-target="filter"
 * - data-filtered-source="[name of filter group in camelCase e.g. contentType]"
 *
 * Apply these data attributes to each item in the list to be filtered:
 * - data-filter-list-target="item"
 * - data-filtered-target-[name of filter group in kebab-case e.g. content-type]='(stringify-ed JSON)' (zero or more)
 */
export default class extends Controller {
  static targets = ["item", "filter", "summary", "url"];
  static values = {group: String};

  /**
   * The initial per item index number, mapped to the filter keys, mapped to the item's values.
   * This is captured at the start so the item filters only need to be calculated once.
   * @type {{[key: number]: {[key: string]: unknown[]}}}
   */
  #initialItemFilterData = {};

  /**
   * The initial filter key mapped to the available options for select elements only.
   *
   * This is captured at the start so the select options can be restored.
   * @type {{[key: string]: {value: string, label: string}[]}}
   */
  #initialSelectOptions = {};

  /**
   * The initial comparison to use for each filter key (filtered-source).
   * Each filter element can have one filtered-source and one comparison-type.
   * Because more than one filter element can have the same filtered-source,
   * each filter key can have more than one comparison type.
   *
   * This is captured at the start because the comparisons are linked to the filter elements,
   * and don't need to be re-built each time.
   * @type {{[key: string]: "exact"|"includes"[]}}
   */
  #initialFilterComparisons = {};

  get initialItemFilterData() {
    return this.#initialItemFilterData;
  }

  connect() {
    this._initItemFilterData();
    this._initVisibility();
    this._initFilterSelectOptions();
    this._initFilterComparisons();

    const filters = this._getFiltersUrlSearch();
    this._setFiltersHtmlElements(filters, {});

    this.filter();
  }

  /**
   * Filter the values of the target items using the values of the target filters.
   */
  filter() {
    // Stop here if there are no items.
    if (!this.hasItemTarget) {
      return;
    }

    const {total, shown, filters, selectedData} = this._filterItems();

    this._setSummary(total, shown);

    // Update the current url to include the filters
    const htmlElementFilters = this._getFiltersHtmlElements();
    this._setFiltersUrlSearch(htmlElementFilters);

    this._setCopyUrl(filters);

    this._setFiltersHtmlElements(filters, selectedData);
  }

  /**
   * Show all files by clearing the filters.
   * @param event
   */
  filterClear(event) {
    // don't follow the url
    event.preventDefault();

    // set the HTML elements to no filter
    const filterTargets = this._getFilterTargets();
    filterTargets.forEach(filterTarget => {
      filterTarget.value = "";
    });

    // update the list of files
    this.filter();
  }

  /**
   * Set the visibility of elements.
   * Use to show only relevant elements depending on whether js is enabled.
   * @private
   */
  _initVisibility() {
    document.querySelectorAll(".initial-toggle-visibility").forEach(item => {
      if (item.classList.contains("hidden")) {
        item.classList.remove("hidden");
      } else {
        item.classList.add("hidden");
      }
    });
  }

  /**
   * Pre-populate the mapping from item, to filter keys, to the item's data used to filter.
   * Performance improvement by avoiding re-calculating the item data.
   * This assumes that the elements will not change after the page has loaded.
   * @private
   */
  _initItemFilterData() {
    const filters = this._getFiltersHtmlElements();

    // reset the item filter mapping data
    this.#initialItemFilterData = {};

    if (!this.hasItemTarget) {
      return;
    }

    this._getItemTargets().forEach((item, index) => {
      const dataAttrs = item.dataset;
      this.#initialItemFilterData[index] = {};
      for (const filterKey in filters) {
        const dataAttrsKey = `filteredTarget${filterKey.charAt(0).toUpperCase()}${filterKey.slice(1)}`;
        const dataAttrValue = dataAttrs[dataAttrsKey];
        if (!dataAttrValue) {
          console.warn(`Item target at index ${index} does not have a value for data attribute '${dataAttrsKey}'.`);
        }
        let value = null;
        try {
          value = JSON.parse(dataAttrValue || "[]");
        } catch {
          value = null;
        }
        if (!Array.isArray(value)) {
          console.warn(`Item target at index ${index} should have an array as value for data attribute '${dataAttrsKey}': ${dataAttrValue}.`);
        }

        this.#initialItemFilterData[index][filterKey] = value ?? [];
      }
    });
  }

  /**
   * Capture the initial select element values, so they can be restored.
   * @returns {void}
   * @private
   */
  _initFilterSelectOptions() {
    this._getFilterTargets().forEach(filterTarget => {
      if (filterTarget.nodeName === "SELECT") {
        const key = filterTarget.dataset.filteredSource;
        if (!this.#initialSelectOptions[key]) {
          this.#initialSelectOptions[key] = [];
        }
        for (const option of filterTarget.options) {
          this.#initialSelectOptions[key].push({value: option.value, label: option.label});
        }
      }
    });
  }

  /**
   * Capture the initial filter element comparisons.
   * @returns {void}
   * @private
   */
  _initFilterComparisons() {
    this._getFilterTargets().forEach(filterTarget => {
      const key = filterTarget.dataset.filteredSource;
      const comparison = filterTarget.dataset.comparisonType;
      if (!this.#initialFilterComparisons[key]) {
        this.#initialFilterComparisons[key] = [];
      }
      if (!this.#initialFilterComparisons[key].includes(comparison)) {
        this.#initialFilterComparisons[key].push(comparison);
      }
    });
  }

  /**
   * Compare an item's data to all filter values and find matches.
   * Filters are processed as 'AND' - the item data must match all the filters.
   * Returns true if all filters are "" or there are no filters.
   * @param itemData {{[key: string]: string[]}} The item mapping.
   * @param filters {{[key: string]: string[]}} The filter mapping.
   * @returns {boolean} True if the item data matches the filter data, otherwise false.
   * @private
   */
  _compare(itemData, filters) {
    for (const [filterKey, filterValuesRaw] of Object.entries(filters)) {
      const filterValues = Array.from(new Set((filterValuesRaw ?? []).map(i => i?.toString()?.trim() ?? "").filter(i => !!i)));
      const itemValues = Array.from(new Set((itemData[filterKey] ?? []).map(i => i?.toString()?.trim() ?? "").filter(i => !!i)));
      const comparisons = this.#initialFilterComparisons[filterKey] ?? [];

      // Not a match if the item values and filter values contain different values.
      if (filterValues.length > 0 && comparisons.includes("exact")) {
        if (!filterValues.every(filterValue => itemValues.includes(filterValue))) {
          return false;
        }
      }

      if (filterValues.length > 0 && comparisons.includes("includes")) {
        if (!filterValues.every(filterValue => itemValues.some(itemValue => itemValue.includes(filterValue)))) {
          return false;
        }
      }
    }
    return true;
  }

  /**
   * Show and hide items based on the filters.
   * @returns {{total: number, shown: number, filters: {[key: string]: string[]}, selectedData: {[key: string]: string[]}}}
   * @private
   */
  _filterItems() {
    const filters = this._getFiltersHtmlElements();
    let total = 0;
    let shown = 0;
    const selectedData = {};

    this._getItemTargets().forEach((item, index) => {
      total += 1;
      const itemData = this.#initialItemFilterData[index];
      const isShow = this._compare(itemData, filters);

      // Should the item be displayed or not?
      if (isShow) {
        // match: show item
        item.classList.remove("hidden");
        shown += 1;
        // store the matched items to update the select options later
        Object.entries(itemData).forEach(([key, values]) => {
          if (!selectedData[key]) {
            selectedData[key] = [];
          }
          values.forEach(value => {
            if (!selectedData[key].includes(value)) {
              selectedData[key].push(value);
            }
          });
        });
      } else {
        // no match: hide item
        item.classList.add("hidden");
      }
    });

    return {
      total: total,
      shown: shown,
      filters: filters,
      selectedData: selectedData,
    };
  }

  /**
   * Get the array of filter targets.
   * @returns {(HTMLSelectElement|HTMLInputElement)[]}
   * @private
   */
  _getFilterTargets() {
    return this.hasFilterTarget ? (this.filterTargets ?? []) : [];
  }

  /**
   * Get the items that are to be filtered.
   * @returns {HTMLElement[]}
   * @private
   */
  _getItemTargets() {
    return this.hasItemTarget ? (this.itemTargets ?? []) : [];
  }

  /**
   * Get the filters from the url query string.
   * @returns {{[key: string]: string[]}}
   * @private
   */
  _getFiltersUrlSearch() {
    const filters = {};
    const enabledFilterTargets = this._getAutoUpdateUrlQuerystringFilters();
    const currentSearchParams = new URLSearchParams(document.location.search);
    const filterTargets = this._getFilterTargets();
    for (const filterTarget of filterTargets) {
      const key = filterTarget.dataset.filteredSource;
      if (!enabledFilterTargets.includes(key)) {
        continue;
      }
      const values = currentSearchParams.getAll(key);
      this._addFilterValue(filters, key, values);
    }
    return filters;
  }

  /**
   * Set the filters to the url query string.
   * @param filters {{[key: string]: string[]}} The filters to set.
   * @returns {void}
   * @private
   */
  _setFiltersUrlSearch(filters) {
    window.history.replaceState(null, "", this._buildFilterUrl(document.location.href, filters));
  }

  /**
   * Get the filters from the HTML element values.
   * @returns {{[key: string]: string[]}}
   * @private
   */
  _getFiltersHtmlElements() {
    const filters = {};
    const filterTargets = this._getFilterTargets();
    for (const filterTarget of filterTargets) {

      let values;
      if (filterTarget.nodeName === "INPUT") {
        values = [filterTarget.value];
      } else if (filterTarget.nodeName === "SELECT") {
        values = Array.from(filterTarget.selectedOptions).map(selectedOption => selectedOption.value);
      } else {
        console.error(`Get HTML filters is not implemented for filter target node name '${filterTarget.nodeName}'.`);
        values = [];
      }

      const key = filterTarget.dataset.filteredSource;
      this._addFilterValue(filters, key, values);
    }
    return filters;
  }

  /**
   * Set the filters to the HTML element values.
   *
   * There are two sources of data: the filter data and the currently selected HTML element values.
   * The goal is to maintain the current HTML element values, and update the available filter options if possible.
   *
   * @param filters {{[key: string]: string[]}} The filters to set.
   * @param selectedData {{[key: string]: string[]}} The shown item values grouped by filter key.
   * @private
   */
  _setFiltersHtmlElements(filters, selectedData) {
    const filterTargets = this._getFilterTargets();
    for (const filterTarget of filterTargets) {
      const key = filterTarget.dataset.filteredSource;
      const values = filters[key] ?? [];

      if (filterTarget.nodeName === "INPUT") {
        this._setFiltersHtmlInputElement(filterTarget, values);
      } else if (filterTarget.nodeName === "SELECT") {
        this._setFiltersHtmlSelectElement(filterTarget, values, selectedData);
      } else {
        console.error(`Set HTML filters is not implemented for filter target node name '${filterTarget.nodeName}'.`);
      }
    }
  }

  /**
   * Set the filter for the HTML input element.
   * @param filterTarget {HTMLInputElement} The input element.
   * @param values {string[]} The filter values.
   * @private
   */
  _setFiltersHtmlInputElement(filterTarget, values) {
    // If no filter value or one value that is empty string: set empty.
    if (values.length === 0) {
      filterTarget.value = "";
    } else if (values.length === 1) {
      filterTarget.value = values[0];
    } else {
      // Use the first filter value.
      const key = filterTarget.dataset.filteredSource;
      console.warn(`Filter input element '${key}' expects zero or one value, but got more than one: ${JSON.stringify(values)}.`);
      filterTarget.value = values[0];
    }
  }

  /**
   * Set the filter for the HTML select element.
   * @param filterTarget {HTMLSelectElement} The select element.
   * @param values {string[]} The filter values.
   * @param selectedData {{[key: string]: string[]}} The shown item values grouped by filter key.
   * @private
   */
  _setFiltersHtmlSelectElement(filterTarget, values, selectedData) {
    const key = filterTarget.dataset.filteredSource;
    const isOnlyEmptyValue = values.length === 0 || (values.length === 1 && values[0] === "");


    // Store which options are currently selected.
    const selectedValues = Array.from(filterTarget.selectedOptions).map(selectedOption => selectedOption.value);

    // Remove all existing options for the filter target in preparation for adding the available options.
    for (let index = filterTarget.options.length - 1; index >= 0; index--) {
      filterTarget.options.remove(index);
    }

    for (const option of this.#initialSelectOptions[key]) {
      const optionValue = option.value;
      const optionLabel = option.label;
      const isEmptyValue = optionValue === "";

      if (isOnlyEmptyValue) {
        // If no filter value or one value that is empty string: select empty value and reduce option list to only available options.
        // This allows the current filter to be refined.

        if (isEmptyValue || (selectedData[key] ?? [])?.includes(optionValue)) {
          const isSelected = isEmptyValue;
          filterTarget.options.add(new Option(optionLabel, optionValue, isSelected, isSelected));
        }

      } else {
        // Include all possible options, then select the filter values.
        // This allows the selection to be changed.

        // Restore the options that were selected before the update.
        const isSelected = selectedValues.includes(optionValue);

        filterTarget.options.add(new Option(optionLabel, optionValue, isSelected, isSelected));
      }
    }
  }

  /**
   * Get a map of the filters and whether they participate in the automatic url querystring update.
   * @returns {string[]}
   * @private
   */
  _getAutoUpdateUrlQuerystringFilters() {
    const filterTargets = this._getFilterTargets();
    return filterTargets
      .map(filterTarget => {
        const key = filterTarget.dataset.filteredSource;
        const value = filterTarget.dataset.autoUpdateUrlQuerystring;
        return [key, value];
      })
      .filter(i => i[1] === "true")
      .map(i => i[0]);
  }

  /**
   * Show the number of matches and the total number of items.
   * @param total {number} The total number of items.
   * @param shown {number} The number of items currently shown.
   * @returns {void}
   * @private
   */
  _setSummary(total, shown) {
    if (this.hasSummaryTarget) {
      let messages = [];
      if (shown === 0) {
        messages.push(gettext("No files match the current filters."));
      }
      messages.push(ngettext(
        "Showing %1 of %2 file.",
        "Showing %1 of %2 files.",
        total,
        shown.toString(),
        total.toString()));
      this.summaryTarget.textContent = messages.join(" ");
    }
  }

  /**
   * Update the direct url to the current filters.
   * @param filters {{[key: string]: string[]}} The existing filter data.
   * @returns {void}
   * @private
   */
  _setCopyUrl(filters) {
    if (this.hasUrlTarget && this.urlTarget) {
      this.urlTarget.href = this._buildFilterUrl(this.urlTarget.href, filters).toString();
    }
  }

  /**
   * Add a value to the filter data.
   * @param filters {{[key: string]: string[]}} The existing filter data.
   * @param filterKey {string} The filter key.
   * @param values {string[]} The values.
   * @returns {void}
   * @private
   */
  _addFilterValue(filters, filterKey, values) {
    if (!values || values.length < 1) {
      return;
    }
    if (!Object.keys(filters).includes(filterKey)) {
      filters[filterKey] = [];
    }
    filters[filterKey].push(...values);
  }

  /**
   * Build a url with the filters in the querystring.
   * @param startUrl {string} The start url.
   * @param filters {{[key: string]: string[]}} The filters to set.
   * @returns {URL}
   * @private
   */
  _buildFilterUrl(startUrl, filters) {
    const enabledFilterTargets = this._getAutoUpdateUrlQuerystringFilters();
    const currentUrl = new URL(startUrl);
    const filterTargets = this._getFilterTargets();

    // Remove all existing search params.
    currentUrl.searchParams.keys().forEach(key => currentUrl.searchParams.delete(key));

    for (const filterTarget of filterTargets) {
      const key = filterTarget.dataset.filteredSource;
      if (!enabledFilterTargets.includes(key)) {
        continue;
      }

      // Add the values to the querystring.
      const values = filters[key] ?? [];
      for (const value of values) {
        if (value) {
          currentUrl.searchParams.append(key, value);
        }
      }
    }
    return currentUrl;
  }
}
