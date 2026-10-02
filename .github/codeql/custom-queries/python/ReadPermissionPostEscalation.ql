/**
 * @name Read permission on POST-capable Pyramid view
 * @description A @view_config decorator guards a view with a read-only
 *              permission while the view handles POST requests that may
 *              perform write/mutation operations. Users with read-only
 *              access can escalate to perform writes.
 * @kind problem
 * @problem.severity warning
 * @precision high
 * @id py/pyramid-read-permission-post-escalation
 * @tags security
 *       authorization
 *       pyramid
 */

import python

/**
 * Holds when `kwValue` is the value expression for keyword argument
 * `kwName` in `call`.
 */
predicate hasKeywordArg(Call call, string kwName, Expr kwValue) {
  exists(Keyword kw |
    kw = call.getAKeyword() and
    kw.getArg() = kwName and
    kw.getValue() = kwValue
  )
}

/**
 * Holds when `attr` is a `Permissions.*` attribute access where the
 * attribute name contains "Read", indicating a read-only permission.
 */
predicate isReadPermission(Attribute attr) {
  attr.getObject().(Name).getId() = "Permissions" and
  attr.getName().matches("%Read%")
}

/**
 * Gets the inner `view_config(...)` call from the outer decorator
 * application `view_config(...)(func)`.
 *
 * Pyramid decorators are parameterized: `@view_config(kwargs)` produces
 * an outer call `view_config(kwargs)(func)` where `getADecoratorCall()`
 * returns the outer call and `.getFunc()` yields the inner call that
 * holds the keyword arguments.
 */
Call getInnerDecoratorCall(Function func) {
  exists(Call outerCall |
    outerCall = func.getDefinition().(FunctionExpr).getADecoratorCall() and
    result = outerCall.getFunc()
  )
}

/**
 * Holds when `innerCall` is a `view_config(...)` decorator on `func`.
 */
predicate isViewConfigDecorator(Call innerCall, Function func) {
  innerCall = getInnerDecoratorCall(func) and
  (
    innerCall.getFunc().(Name).getId() = "view_config"
    or
    innerCall.getFunc().(Attribute).getName() = "view_config"
  )
}

/**
 * Holds when the decorator call explicitly sets `request_method="GET"`,
 * meaning it only handles GET requests.
 */
predicate hasExplicitGetMethod(Call innerCall) {
  exists(Expr v |
    hasKeywordArg(innerCall, "request_method", v) and
    v.(StringLiteral).getText() = "GET"
  )
}

/**
 * Holds when the decorator call sets `require_methods=["POST"]`,
 * making it a POST-only view.
 */
predicate hasRequireMethodsPost(Call innerCall) {
  exists(List lst |
    hasKeywordArg(innerCall, "require_methods", lst) and
    lst.getAnElt().(StringLiteral).getText() = "POST"
  )
}

/**
 * Holds when the decorator call sets `request_method="POST"`.
 */
predicate hasRequestMethodPost(Call innerCall) {
  exists(Expr v |
    hasKeywordArg(innerCall, "request_method", v) and
    v.(StringLiteral).getText() = "POST"
  )
}

/**
 * Holds when the decorator call sets `require_methods=False`,
 * allowing all HTTP methods (GET + POST).
 */
predicate hasRequireMethodsFalse(Call innerCall) {
  exists(Expr v |
    hasKeywordArg(innerCall, "require_methods", v) and
    v instanceof False
  )
}

/**
 * Holds when the function body contains a comparison
 * `request.method == "POST"`, indicating it handles POST internally.
 */
predicate bodyChecksPostMethod(Function func) {
  exists(Compare cmp, Attribute left, StringLiteral right |
    cmp.getScope() = func and
    cmp.getLeft() = left and
    left.getName() = "method" and
    cmp.getComparator(0) = right and
    right.getText() = "POST" and
    cmp.getOp(0) instanceof Eq
  )
}

/**
 * Sub-pattern A: @view_config with require_methods=False, a read-only
 * permission, and the function body checks request.method == "POST".
 */
predicate subpatternA(Call innerCall, Function func, Attribute permAttr) {
  isViewConfigDecorator(innerCall, func) and
  hasKeywordArg(innerCall, "permission", permAttr) and
  isReadPermission(permAttr) and
  hasRequireMethodsFalse(innerCall) and
  bodyChecksPostMethod(func) and
  not hasExplicitGetMethod(innerCall)
}

/**
 * Sub-pattern B: @view_config that is POST-only
 * (require_methods=["POST"] or request_method="POST") but uses a
 * read-only permission.
 */
predicate subpatternB(Call innerCall, Function func, Attribute permAttr) {
  isViewConfigDecorator(innerCall, func) and
  hasKeywordArg(innerCall, "permission", permAttr) and
  isReadPermission(permAttr) and
  (
    hasRequireMethodsPost(innerCall) or
    hasRequestMethodPost(innerCall)
  ) and
  not hasExplicitGetMethod(innerCall)
}

from Call innerCall, Function func, Attribute permAttr, string msg
where
  (
    subpatternA(innerCall, func, permAttr) and
    msg =
      "View '" + func.getName() +
      "' uses read-only permission " + permAttr.getName() +
      " with require_methods=False but handles POST requests." +
      " POST operations may need a write permission."
  )
  or
  (
    subpatternB(innerCall, func, permAttr) and
    msg =
      "View '" + func.getName() +
      "' is POST-only but uses read-only permission " +
      permAttr.getName() +
      ". POST-only views should use a write/manage permission."
  )
select innerCall, msg
