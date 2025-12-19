/* SPDX-License-Identifier: Apache-2.0 */


/*
 * This controller enables filtering a list using either input or select elements.
 * Each element can filter on a separate data attribute applied to items in the list to be filtered.
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
import {Controller} from "@hotwired/stimulus";
import {gettext, ngettext} from "../utils/messages-access";

export default class extends Controller {
  static targets = ["item", "filter", "summary", "url"];
  static values = {
    group: String,
  };

  mappingItemFilterData = {};
  initialSelectOptions = {};

  connect() {
    this._populateMappings();
    this._initVisibility();

    // Capture the initial select element values, so they can be restored.
    this._getFilterTargets().forEach(filterTarget => {
      if (filterTarget.nodeName === "SELECT") {
        const key = filterTarget.dataset.filteredSource;
        if (!this.initialSelectOptions[key]) {
          this.initialSelectOptions[key] = [];
        }
        for (const option of filterTarget.options) {
          this.initialSelectOptions[key].push([option.value, option.label]);
        }
      }
    });

    const urlFilters = this._getFiltersUrlSearch();
    this._setFiltersHtmlElements(urlFilters);

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

    const {total, shown, groupedLabels} = this._filterItems();

    this._setSummary(total, shown);

    // Update the current url to include the filters
    const htmlElementFilters = this._getFiltersHtmlElements();
    this._setFiltersUrlSearch(htmlElementFilters);

    this._setCopyUrl();

    this._setFilters(groupedLabels);
  }

  /**
   * Show all files by clearing the filters.
   * @param event
   */
  filterClear(event) {
    // don't follow the url
    event.preventDefault();

    // set the html elements to no filter
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
  _populateMappings() {
    const filterData = this._getFilters();

    // reset the item filter mapping data
    this.mappingItemFilterData = {};

    if (!this.hasItemTarget) {
      return;
    }

    this._getItemTargets().forEach((item, index) => {
      const dataAttrs = item.dataset;
      this.mappingItemFilterData[index] = {};
      for (const filterKey in filterData) {
        const dataAttrsKey = `filteredTarget${filterKey.charAt(0).toUpperCase()}${filterKey.slice(1)}`;
        const dataAttrValue = dataAttrs[dataAttrsKey];
        if (!dataAttrValue) {
          console.warn(`Item target at index ${index} does not have a value for data attribute '${dataAttrsKey}'.`);
        }
        this.mappingItemFilterData[index][filterKey] = JSON.parse(dataAttrValue || "[]");
      }
    });

  }

  /**
   * Compare an item's data to all filter values and find matches.
   * Filters are processed as 'AND' - the item data must match all the filters.
   * Returns true if all filters are "" or there are no filters.
   * @param itemData {{[key: string]:string[]}} The item mapping.
   * @param filterData {{[key: string]: {[comparison: "exact"|"includes"]: values: string[]}}} The filter mapping.
   * @returns {boolean} True if the item data matches the filter data, otherwise false.
   * @private
   */
  _compare(itemData, filterData) {
    for (const [filterKey, filterInfo] of Object.entries(filterData)) {
      for (const [comparison, filterValuesRaw] of Object.entries(filterInfo)) {
        const filterValues = Array.from(new Set((filterValuesRaw ?? []).map(i => i?.toString()?.trim() ?? "").filter(i => !!i)));
        const itemValues = Array.from(new Set((itemData[filterKey] ?? []).map(i => i?.toString()?.trim() ?? "").filter(i => !!i)));

        // Not a match if the item values and filter values contain different values.
        if (filterValues.length > 0 && comparison === "exact") {
          if (!filterValues.every(filterValue => itemValues.includes(filterValue))) {
            return false;
          }
        }

        if (filterValues.length > 0 && comparison === "includes") {
          if (!filterValues.every(filterValue => itemValues.some(itemValue => itemValue.includes(filterValue)))) {
            return false;
          }
        }
      }
    }
    return true;
  }

  /**
   * Show and hide items based on the filters.
   * @returns {{total: number, shown: number, groupedLabels: {[key: string]: string[]}}}
   * @private
   */
  _filterItems() {
    const filterData = this._getFilters();
    let total = 0;
    let shown = 0;
    const groupedLabels = {};

    this._getItemTargets().forEach((item, index) => {
      total += 1;
      const itemData = this.mappingItemFilterData[index];
      const isShow = this._compare(itemData, filterData);

      // Should the item be displayed or not?
      if (isShow) {
        // match: show item
        item.classList.remove("hidden");
        shown += 1;
        // store the matched items to update the select options later
        Object.entries(itemData).forEach(([key, values]) => {
          if (!groupedLabels[key]) {
            groupedLabels[key] = [];
          }
          values.forEach(value => {
            if (!groupedLabels[key].includes(value)) {
              groupedLabels[key].push(value);
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
      groupedLabels: groupedLabels,
    }
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
   * Build a mapping of filteredSource names, to comparison, to array of values.
   * @returns {{[key: string]: {[comparison: "exact"|"includes"]: values: string[]}}}
   * @private
   */
  _getFilters() {
    const filterData = {};
    const filterTargets = this._getFilterTargets();
    filterTargets.forEach(filterTarget => {
      const key = filterTarget.dataset.filteredSource;

      let values;
      if (filterTarget.nodeName === "INPUT") {
        values = [filterTarget.value];
      } else if (filterTarget.nodeName === "SELECT") {
        values = Array.from(filterTarget.selectedOptions).map(selectedOption => selectedOption.value);
      } else {
        console.error(`Get filters is not implemented for filter target node name '${filterTarget.nodeName}'.`);
        values = [];
      }

      const comparison = filterTarget.dataset.comparisonType;
      if (!Object.keys(filterData).includes(key)) {
        filterData[key] = {};
      }
      if (!Object.keys(filterData[key]).includes(comparison)) {
        filterData[key][comparison] = [];
      }
      filterData[key][comparison].push(...values);
    });
    return filterData;
  }

  /**
   * Update the dropdowns to reflect the currently displayed items.
   * Selection filters that have a selection will show all options, to allow changing the selection.
   * Selection filters that do not have a selection will have their options reduced to only the available options.
   * @param filter {{[key: string]:  string[]}} The map of filteredSource to array of available values.
   * @private
   */
  _setFilters(filter) {
    const filterTargets = this._getFilterTargets();
    for (const filterTarget of filterTargets) {
      const key = filterTarget.dataset.filteredSource;
      const values = filter[key] ?? [];

      if (filterTarget.nodeName === "INPUT") {
        // An input filter can't have multiple values, just use the first.
        filterTarget.value = values.length > 0 ? values[0] : "";
      } else if (filterTarget.nodeName === "SELECT") {
        // Store which options are currently selected.
        const selectedValues = Array.from(filterTarget.selectedOptions).map(selectedOption => selectedOption.value);
        const hasSelectedNonEmptyOptions = selectedValues && selectedValues.length > 0 && selectedValues.some(value => value !== "");

        // Remove all existing options for the filter target in preparation for adding the available options.
        for (let index = filterTarget.options.length - 1; index >= 0; index--) {
          filterTarget.options.remove(index);
        }

        // Add the options reflecting the currently displayed items.
        // Filter targets with a non-empty selection keep all their options, so that all the options are available to change the selection.
        for (const initialOption of this.initialSelectOptions[key]) {
          const initialOptionValue = initialOption[0];
          const initialOptionLabel = initialOption[1];
          if (initialOptionValue === "") {
            // Empty value representing no selection is always present, and selected if nothing else is selected.
            const isSelected = !hasSelectedNonEmptyOptions;
            filterTarget.options.add(new Option(initialOptionLabel, initialOptionValue, null, isSelected));
          } else if (values.includes(initialOptionValue) && !hasSelectedNonEmptyOptions) {
            // Include only values to keep when nothing is selected.
            filterTarget.options.add(new Option(initialOptionLabel, initialOptionValue, null, false));
          } else if (hasSelectedNonEmptyOptions) {
            //
            const isSelected = selectedValues.includes(initialOptionValue);
            filterTarget.options.add(new Option(initialOptionLabel, initialOptionValue, null, isSelected));
          }
        }
      }
    }
  }

  /**
   * Get the filters from the url query string.
   * @returns {{[key: string]: string}}
   * @private
   */
  _getFiltersUrlSearch() {
    const enabledFilterTargets = this._getAutoUpdateUrlQuerystringFilters();
    const currentSearchParams = new URLSearchParams(document.location.search);
    const filterTargets = this._getFilterTargets();
    return Object.fromEntries(filterTargets.map(filterTarget => {
      const key = filterTarget.dataset.filteredSource;
      const value = currentSearchParams.get(key);
      return [key, value];
    }).filter(i => enabledFilterTargets.includes(i[0])));
  }

  /**
   * Set the filters to the url query string.
   * @param filters {{[key: string]: string}} The filters to set.
   * @private
   */
  _setFiltersUrlSearch(filters) {
    const enabledFilterTargets = this._getAutoUpdateUrlQuerystringFilters();
    const currentUrl = new URL(document.location.href);
    const filterTargets = this._getFilterTargets();
    filterTargets.forEach(filterTarget => {
      const key = filterTarget.dataset.filteredSource;
      if (!enabledFilterTargets.includes(key)) {
        return;
      }
      const value = filters[key] ?? null;
      if (value) {
        currentUrl.searchParams.set(key, value);
      } else {
        currentUrl.searchParams.delete(key);
      }
    });
    window.history.replaceState(null, "", currentUrl);
  }

  /**
   * Get the filters from the HTML element values.
   * @returns {{[key: string]: string}}
   * @private
   */
  _getFiltersHtmlElements() {
    const filterTargets = this._getFilterTargets();
    return Object.fromEntries(filterTargets.map(filterTarget => {
      const key = filterTarget.dataset.filteredSource;
      const value = filterTarget.value;
      return [key, value];
    }));
  }

  /**
   * Set the filters to the HTML element values.
   * @param filters {{[key: string]: string}} The filters to set.
   * @private
   */
  _setFiltersHtmlElements(filters) {
    const filterTargets = this._getFilterTargets();
    filterTargets.forEach(filterTarget => {
      const key = filterTarget.dataset.filteredSource;
      if (filters[key] !== undefined) {
        filterTarget.value = filters[key] ?? "";
      }
    });
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
   * @private
   */
  _setCopyUrl() {
    if (this.hasUrlTarget && this.urlTarget) {
      const htmlElementFilters = this._getFiltersHtmlElements();
      const urlTargetUrl = new URL(this.urlTarget.href);
      for (const [key, value] of Object.entries(htmlElementFilters ?? {})) {
        if (value) {
          urlTargetUrl.searchParams.set(key, value);
        } else {
          urlTargetUrl.searchParams.delete(key);
        }
      }
      this.urlTarget.textContent = urlTargetUrl.toString();
    }
  }
}
