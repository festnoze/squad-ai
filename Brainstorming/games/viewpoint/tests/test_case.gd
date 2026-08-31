class_name ViewTest
extends RefCounted
## Base class for every suite under tests/. Same harness as the other Godot
## games of the repo: a suite exposes test_ methods, records checks, and must
## call done() as its last statement so an aborted method cannot pass silently.

var failures: PackedStringArray = PackedStringArray()
var checks: int = 0

## Set by done(). The runner treats a false value as an aborted method.
var finished: bool = false


func suite_name() -> String:
	return "suite sans nom"


## Mandatory last statement of every test method.
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


func fail(message: String) -> void:
	checks += 1
	failures.append(message)
