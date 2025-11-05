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
      if (filterTarget.nodeName === 'SELECT') {
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

    const filterData = this._buildFilterData();

    let total = 0;
    let shown = 0;

    const groupedLabels = {};

    this.itemTargets.forEach((item, index) => {
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
          })
        });
      } else {
        // no match: hide item
        item.classList.add("hidden");
      }
    });

    // show the number of matches and the total number of items
    if (this.hasSummaryTarget) {
      let messages = [];
      if (shown === 0) {
        messages.push(gettext("No files match the current filters."));
      }
      messages.push(ngettext(
        "Showing %1 of %2 file.",
        "Showing %1 of %2 files.",
        total,
        shown,
        total));
    this.summaryTarget.textContent = messages.join(' ');
  }

    // Update the current url to include the filters
    const htmlElementFilters = this._getFiltersHtmlElements();
    this._setFiltersUrlSearch(htmlElementFilters);

    // Update the direct url to these filters
    if (this.hasUrlTarget && this.urlTarget) {
      const urlTargetUrl = new URL(this.urlTarget.href);
      Object.entries(htmlElementFilters ?? {}).forEach(([key, value]) => {
        if (value) {
          urlTargetUrl.searchParams.set(key, value);
        } else {
          urlTargetUrl.searchParams.delete(key);
        }
      });
      this.urlTarget.textContent = urlTargetUrl.toString();
    }

    // Update the dropdowns to reflect the currently displayed items.
    const filterTargets = this._getFilterTargets();
    const selected = {};
    filterTargets.forEach(filterTarget => {
      if (filterTarget.nodeName === 'SELECT') {
        const key = filterTarget.dataset.filteredSource;
        // Store which option is selected.
        for (const selectedOption of filterTarget.selectedOptions) {
          selected[key] = selectedOption.value;
        }
        // Remove all existing options.
        for (let index = filterTarget.options.length - 1; index >= 0; index--) {
          filterTarget.options.remove(index);
        }
        // Add the options reflecting the currently displayed items.
        const valuesToKeep = groupedLabels[key] ?? [];
        this.initialSelectOptions[key].forEach(option => {
          const initialOptionValue = option[0];
          const initialOptionLabel = option[1];
          if (initialOptionValue === "" || valuesToKeep.includes(initialOptionValue)) {
            const isSelected = selected[key] === initialOptionValue;
            filterTarget.options.add(new Option(initialOptionLabel, initialOptionValue, null, isSelected));
          }
        });
      }
    });
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
    const filterData = this._buildFilterData();

    // reset the item filter mapping data
    this.mappingItemFilterData = {};

    if (!this.hasItemTarget) {
      return;
    }

    this.itemTargets.forEach((item, index) => {
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
   * Build a mapping of filteredSource names to array of values.
   * @returns {{[key: string]: {values: string[], comparison: "exact"|"includes"}}}
   * @private
   */
  _buildFilterData() {
    const filterData = {};
    const filterTargets = this._getFilterTargets();
    filterTargets.forEach(filterTarget => {
      const key = filterTarget.dataset.filteredSource;
      const value = filterTarget.value;
      if (!Object.hasOwn(filterData, key)) {
        filterData[key] = {values: [], comparison: 'exact'};
      }
      filterData[key].values.push(value);

      const comparison = filterTarget.dataset.comparisonType;
      if (comparison) {
        filterData[key].comparison = comparison;
      }
    });
    return filterData;
  }

  /**
   * Compare an item's data to all filter values and find matches.
   * Filters are processed as 'AND' - the item data must match all the filters.
   * @param itemData {{[key: string]:string[]}} The item mapping.
   * @param filterData {{[key: string]: {values: string[], comparison: "exact"|"includes"}}} The filter mapping.
   * @returns {boolean}
   * @private
   */
  _compare(itemData, filterData) {
    for (const [filterKey, filterInfo] of Object.entries(filterData)) {
      const comparison = filterInfo.comparison;
      const filterValues = Array.from(new Set((filterInfo.values ?? []).map(i => i?.toString()?.trim() ?? "").filter(i => !!i)));
      const itemValues = Array.from(new Set((itemData[filterKey] ?? []).map(i => i?.toString()?.trim() ?? "").filter(i => !!i)));

      // Not a match if the item values and filter values contain different values.
      if (filterValues.length > 0 && comparison === 'exact') {
        if (!filterValues.every(filterValue => itemValues.includes(filterValue))) {
          return false;
        }
      }

      if (filterValues.length > 0 && comparison === 'includes') {
        if (!filterValues.every(filterValue => itemValues.some(itemValue => itemValue.includes(filterValue)))) {
          return false;
        }
      }
    }
    return true;
  }

  _getFilterTargets() {
    return this.hasFilterTarget ? (this.filterTargets ?? []) : [];
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
    }).filter(([key, _value]) => enabledFilterTargets.includes(key)));
  }

  /**
   * Set the filters to the url query string.
   * @param filters The filters to set.
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
   * @param filters
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
      .filter(([_key, value]) => value === 'true')
      .map(([key, _value]) => key);
  }
}
