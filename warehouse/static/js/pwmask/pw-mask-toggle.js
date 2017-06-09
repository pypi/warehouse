/* Licensed under the Apache License, Version 2.0 (the "License");
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

/**
 * This code is based upon freely redistributable example code published by
 * Geoffrey Crofte on codepen.io. Below is the license included with his code.
 *
 * ***************************************************************************
 * Copyright (c) 2017 by Geoffrey Crofte (http://codepen.io/CreativeJuiz/pen/cvyEi)
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is furnished
 * to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
 * PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
 * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
 * OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
 * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 * ***************************************************************************
 */


/*****************************************************************************
 * This event handler is invoked when the submit button in the login.html and
 * register.html page is clicked. The purpose is to remove the "Show password"
 * checkbox element, thus prevent polluting the POST request.
 */

$(".-js-pw-m-sbt").on("submit", function () {
  $("#-js-pw-m-lbl").remove();
  return true;
});


/*****************************************************************************
 * This code is invoked when the "Show password" checkbox is clicked
 * thus changing it value from "On" to "Off". It toggles the "password*"
 * input element type attribute from "password" to "text" and vice-versa.
 *
 * This checkbox is identified by the CSS seleector "-js-pw-m-fld".
 *
 * **NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**
 *
 *       The following code **requires** the jQuery library!
 *
 * **NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**NOTE**
 *
 */
$(".-js-pw-m-cbx").on("change", function(){
  var element = document.querySelectorAll(".-js-pw-m-fld");
  for (var elem of element) {
    if($(elem).attr("type") === "password")
      changeType($(elem), "text");
    else
      changeType($(elem), "password");
  }
  return false;
});


/* 
 * Loosely based on a function from : https://gist.github.com/3559343
 * Thank you bminer!
 *
 * Function Name:
 *     changeType(x, type)
 *
 * Parameters:
 *     x    => The "password" input element to be manipulated.
 *     type => A string that is assigned to the x.type attribute.
 *
 * NOTE:
 *   The only values accepted for the *type* parameter are "text"
 *   and "password".  All other values are silently ignored.
 */

function changeType(x, type) {
  if(type !== "text" && type !== "password")
    return true; // Ignore unknown "type". Yes, I'm a bit paranoid. ;-)

  if(x.attr("type") === type)
    return true; // Attribute already set to "type". Nothing to do.

  try {       // Modify the password element "type" attribute
    return x.attr("type", type); // Stupid IE security will not allow this
  } catch(e) {
    // Try re-creating the input element (yep... this sucks)
    // Clone the existing element
    var tmp = x.clone(true, true);

    // Now set the element type to whatever value was passed to us
    // in the :type: parameter. We can get away with this because
    // this copy of the element is not in the DOM ... yet.
    tmp.attr("type", type);

    // Replace the existing input element with our shiny new one (*Surprise IE* :-)
    x.replaceWith(tmp);
    return true;
  }
}
