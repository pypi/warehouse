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
import {ngettext} from "../utils/messages-access";

export default class extends Controller {
  static targets = ["item", "filter", "summary", "url"];
  static values = {
    group: String,
  };

  mappingItemFilterData = {};

  connect() {
    this._populateMappings();
    this._initVisibility();

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

    this.itemTargets.forEach((item, index) => {
      total += 1;
      const itemData = this.mappingItemFilterData[index];
      const compareResult = this._compare(itemData, filterData);

      // Should the item be displayed or not?
      // Show if there are no filters, or if there are filters and at least one match.
      const isShow = !compareResult.hasFilter || (compareResult.hasFilter && compareResult.isMatch);
      if (isShow) {
        // match: show item
        item.classList.remove("hidden");
        shown += 1;
      } else {
        // no match: hide item
        item.classList.add("hidden");
      }
    });

    // show the number of matches and the total number of items
    if (this.hasSummaryTarget) {
      this.summaryTarget.textContent = ngettext(
        "Showing %1 of %2 file.",
        "Showing %1 of %2 files.",
        total,
        shown,
        total);
    }

    // Update the direct url to this filter
    if (this.hasUrlTarget && this.urlTarget) {
      const searchParams = new URLSearchParams();
      for (const key in filterData) {
        for (const value of filterData[key]) {
          if (value && value.trim()) {
            searchParams.set(key, [...searchParams.getAll(key), value]);
          }
        }
      }

      const qs = searchParams.toString();
      const baseUrl = new URL(this.urlTarget.href);
      if (qs) {
        baseUrl.search = "?" + qs;
      }
      this.urlTarget.textContent = baseUrl.toString();
    }
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
   * @returns {{}}
   * @private
   */
  _buildFilterData() {
    const filterData = {};
    if (this.hasFilterTarget) {
      this.filterTargets.forEach(filterTarget => {
        const key = filterTarget.dataset.filteredSource;
        const value = filterTarget.value;
        if (!Object.hasOwn(filterData, key)) {
          filterData[key] = [];
        }
        filterData[key].push(value);
      });
    }
    return filterData;
  }

  /**
   * Compare an item's tags to all filter values and find matches.
   * @param itemData The item mapping.
   * @param filterData The filter mapping.
   * @returns {{hasFilter: boolean, isMatch: boolean, matches: *[]}}
   * @private
   */
  _compare(itemData, filterData) {
    // The overall match will be true when,
    // for every filter key that has at least one value,
    // at least one item value for the same key includes any filter value.

    const isMatch = [];
    const matches = [];
    const misses = [];
    let hasFilter = false;
    for (const itemKey in itemData) {
      const itemValues = itemData[itemKey];
      const filterValues = filterData[itemKey];

      let isKeyMatch = false;
      let hasKeyFilter = false;

      for (const itemValue of itemValues) {
        for (const filterItemValue of filterValues) {

          if (filterItemValue && !hasKeyFilter) {
            // Record whether there are any filter values in any filter key.
            hasFilter = true;
          }

          if (filterItemValue && !hasKeyFilter) {
            // Record whether there are any filter values in *this* filter key.
            hasKeyFilter = true;
          }

          // There could be two types of comparisons - exact match for tags, contains for filename.
          // Using: for each named group, does any item value include any filter value?
          if (filterItemValue && itemValue.includes(filterItemValue)) {
            isKeyMatch = true;
            matches.push({"key": itemKey, "filter": filterItemValue, "item": itemValue});
          }
          if (filterItemValue && !itemValue.includes(filterItemValue)) {
            misses.push({"key": itemKey, "filter": filterItemValue, "item": itemValue});
          }
        }
      }
      isMatch.push(!hasKeyFilter || (isKeyMatch && hasKeyFilter));
    }

    return {
      "isMatch": isMatch.every(value => value),
      "hasFilter": hasFilter,
      "matches": matches,
      "misses": misses,
    };
  }
}
