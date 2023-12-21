/**
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


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
 * - data-filtered-target-[name of filter group in kebab-case e.g. content-type]="[a list joined by '--;--']" (zero or more)
 */
import {Controller} from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["item", "filter", "total", "shown"];
  static values = {
    group: String,
  };

  static _listSep = "--;--";

  connect() {

    this.filterTimeout = null;

    this.filter();
  }

  /**
   * Filter the values of the target items using the values of the target filters.
   */
  filter() {
    // Stop here if there are no items.
    if (!this.hasItemTarget) {
      console.debug("There are no built distribution wheel files to filter.");
      return;
    }

    const filterData = this._buildFilterData();

    let total = 0;
    let shown = 0;

    this.itemTargets.forEach(item => {
      total += 1;
      const itemData = this._buildItemData(item, filterData);
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

    this.shownTarget.textContent = shown.toString();
    this.totalTarget.textContent = total.toString();

    console.debug(`Filtered built distribution wheel files. Now showing ${shown} of ${total}.`);
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
   * Build a mapping of filteredTarget names to array of values.
   * @param item The item element.
   * @param filterData The filter mapping.
   * @returns {{}}
   * @private
   */
  _buildItemData(item, filterData) {
    const dataAttrs = item.dataset;
    const itemData = {};
    for (const filterKey in filterData) {
      itemData[filterKey] = dataAttrs[`filteredTarget${filterKey.charAt(0).toUpperCase()}${filterKey.slice(1)}`].split(this._listSep);
    }
    return itemData;
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
    let matches = [];
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
        }
      }
      isMatch.push(!hasKeyFilter || (isKeyMatch && hasKeyFilter));
    }

    return {
      "isMatch": isMatch.every(value => value),
      "hasFilter": hasFilter,
      "matches": matches,
    };
  }
}
