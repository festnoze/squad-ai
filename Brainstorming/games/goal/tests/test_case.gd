class_name GoalTest
extends RefCounted
## Base class for every suite under tests/.
##
## A suite subclasses this and exposes methods whose names start with "test_".
## The runner discovers them by reflection, calls each one on a fresh instance,
## and reports whatever landed in `failures`.
##
## GDScript has no exceptions, so a runtime error inside a test method aborts
## that method and hands control straight back to the runner with no signal that
## anything went wrong. A suite full of calls to a misspelled function would
## therefore report a cheerful zero failures. Two rules close that hole, and both
## are enforced by the runner:
##
##   1. A method that records no check at all is a failure.
##   2. Every test method must call done() as its last statement. A method that
##      never reaches it was interrupted, and the runner says so.

var failures: PackedStringArray = PackedStringArray()
var checks: int = 0

## Set by done(). The runner treats a false value as an aborted method.
var finished: bool = false


## Name shown in the report. Override for something friendlier than the path.
func suite_name() -> String:
	return "suite sans nom"


## Mandatory last statement of every test method. See the class comment.
func done() -> void:
	finished = true


func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)


func eq(actual: Variant, expected: Variant, message: String) -> void:
	checks += 1
	if actual != expected:
		failures.append("%s (attendu %s, obtenu %s)" % [message, str(expected), str(actual)])


func ne(actual: Variant, forbidden: Variant, message: String) -> void:
	checks += 1
	if actual == forbidden:
		failures.append("%s (valeur interdite %s)" % [message, str(forbidden)])


func near(actual: float, expected: float, tolerance: float, message: String) -> void:
	checks += 1
	if absf(actual - expected) > tolerance:
		failures.append("%s (attendu %f +/- %f, obtenu %f)" % [message, expected, tolerance, actual])


func between(actual: float, low: float, high: float, message: String) -> void:
	checks += 1
	if actual < low or actual > high:
		failures.append("%s (attendu dans [%f, %f], obtenu %f)" % [message, low, high, actual])


## Vector comparison with a per axis tolerance. Reports the whole vector so a
## failure says which axis drifted rather than just "not equal".
func near_vec(actual: Vector3, expected: Vector3, tolerance: float, message: String) -> void:
	checks += 1
	if actual.distance_to(expected) > tolerance:
		failures.append("%s (attendu %s +/- %f, obtenu %s)" % [message, str(expected), tolerance, str(actual)])


func fail(message: String) -> void:
	checks += 1
	failures.append(message)
