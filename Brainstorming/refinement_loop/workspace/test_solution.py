"""
Tests pytest pour le module solution.py — recherche des nombres premiers.

Couverture :
  - Correction        : valeurs attendues connues, ordre, unicité.
  - Edge cases        : n négatif, types invalides, n très grand.
  - Performance       : mesure du temps d'exécution pour N in [100, 1000, 10_000, 100_000].
"""

import time
import math
import pytest

from solution import find_primes, _sieve, _upper_bound

# Détection optionnelle de pytest-benchmark
try:
    import pytest_benchmark  # noqa: F401
    HAS_BENCHMARK = True
except ImportError:
    HAS_BENCHMARK = False


# ===========================================================================
# Données de référence
# ===========================================================================

# Les 25 premiers nombres premiers (OEIS A000040)
FIRST_25_PRIMES = [
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29,
    31, 37, 41, 43, 47, 53, 59, 61, 67, 71,
    73, 79, 83, 89, 97,
]

# Quelques jalons bien connus
PRIME_100  = 541    # 100e  nombre premier
PRIME_1000 = 7919   # 1000e nombre premier


# ===========================================================================
# Classe 1 — Correction
# ===========================================================================

class TestCorrectness:
    """Vérifie que find_primes retourne exactement les bons résultats."""

    def test_zero_returns_empty_list(self):
        """find_primes(0) doit retourner une liste vide."""
        result = find_primes(0)
        assert result == [], f"Attendu [], obtenu {result}"

    def test_one_returns_first_prime(self):
        """find_primes(1) doit retourner [2]."""
        assert find_primes(1) == [2]

    def test_two_returns_first_two_primes(self):
        """find_primes(2) doit retourner [2, 3]."""
        assert find_primes(2) == [2, 3]

    def test_five_returns_first_five_primes(self):
        """find_primes(5) doit retourner [2, 3, 5, 7, 11]."""
        assert find_primes(5) == [2, 3, 5, 7, 11]

    def test_ten_returns_first_ten_primes(self):
        """find_primes(10) doit retourner les 10 premiers premiers (OEIS A000040)."""
        expected = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        assert find_primes(10) == expected

    def test_twenty_five_primes(self):
        """find_primes(25) doit correspondre aux 25 premiers connus."""
        assert find_primes(25) == FIRST_25_PRIMES

    def test_100th_prime(self):
        """Le centième nombre premier doit être 541."""
        result = find_primes(100)
        assert len(result) == 100
        assert result[-1] == PRIME_100, f"100e premier attendu: {PRIME_100}, obtenu: {result[-1]}"

    def test_1000th_prime(self):
        """Le millième nombre premier doit être 7919."""
        result = find_primes(1000)
        assert len(result) == 1000
        assert result[-1] == PRIME_1000, f"1000e premier attendu: {PRIME_1000}, obtenu: {result[-1]}"

    def test_result_length_matches_n(self):
        """La liste retournée doit avoir exactement n éléments."""
        for n in [0, 1, 5, 10, 50, 100, 500]:
            result = find_primes(n)
            assert len(result) == n, f"find_primes({n}) retourne {len(result)} éléments, attendu {n}"

    def test_results_are_sorted_ascending(self):
        """Les nombres premiers doivent être triés en ordre croissant."""
        result = find_primes(200)
        assert result == sorted(result), "Les résultats ne sont pas triés."

    def test_no_duplicates(self):
        """Chaque nombre premier ne doit apparaître qu'une seule fois."""
        result = find_primes(200)
        assert len(result) == len(set(result)), "Des doublons ont été détectés."

    def test_all_results_are_prime(self):
        """Chaque élément retourné doit effectivement être premier."""
        result = find_primes(50)
        for p in result:
            assert _is_prime_naive(p), f"{p} n'est pas un nombre premier."

    def test_no_composite_missed(self):
        """Aucun nombre premier <= au dernier résultat ne doit être absent."""
        result = find_primes(50)
        max_val = result[-1]
        expected = [i for i in range(2, max_val + 1) if _is_prime_naive(i)]
        assert result == expected, "Des nombres premiers ont été omis."

    def test_return_type_is_list(self):
        """Le type de retour doit être une liste Python."""
        assert isinstance(find_primes(0), list)
        assert isinstance(find_primes(5), list)

    def test_elements_are_integers(self):
        """Chaque élément de la liste doit être un entier Python."""
        result = find_primes(20)
        for p in result:
            assert isinstance(p, int), f"{p!r} n'est pas un int."

    def test_all_results_greater_than_one(self):
        """Tous les nombres premiers doivent être > 1."""
        result = find_primes(100)
        assert all(p > 1 for p in result), "Un résultat est <= 1."

    def test_first_prime_is_two(self):
        """Le premier nombre premier doit toujours être 2."""
        for n in [1, 2, 10, 100]:
            assert find_primes(n)[0] == 2

    @pytest.mark.parametrize("n, expected_last", [
        (1,    2),
        (2,    3),
        (3,    5),
        (4,    7),
        (5,   11),
        (6,   13),
        (10,  29),
        (20,  71),
        (25,  97),
    ])
    def test_nth_prime_parametrized(self, n, expected_last):
        """Vérifie le n-ième premier pour des jalons connus."""
        result = find_primes(n)
        assert result[-1] == expected_last, (
            f"find_primes({n})[-1] == {result[-1]}, attendu {expected_last}"
        )


# ===========================================================================
# Classe 2 — Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Vérifie le comportement aux frontières et pour les entrées invalides."""

    # --- Types invalides → TypeError ---

    def test_float_raises_type_error(self):
        with pytest.raises(TypeError):
            find_primes(10.0)

    def test_string_raises_type_error(self):
        with pytest.raises(TypeError):
            find_primes("10")

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            find_primes(None)

    def test_list_raises_type_error(self):
        with pytest.raises(TypeError):
            find_primes([10])

    def test_bool_raises_type_error(self):
        """bool est sous-classe de int en Python ; vérifie si c'est rejeté."""
        # bool est techniquement int ; on vérifie le comportement documenté.
        # Si la fonction accepte True/False, on vérifie la cohérence du résultat.
        # find_primes(True) == find_primes(1) ou TypeError — les deux sont valides.
        try:
            result = find_primes(True)
            # Si accepté, True == 1, donc résultat attendu = [2]
            assert result == [2], f"find_primes(True) retourne {result}, attendu [2]"
        except TypeError:
            pass  # Rejet explicite des booléens : acceptable

    def test_complex_raises_type_error(self):
        with pytest.raises(TypeError):
            find_primes(3 + 0j)

    # --- Valeurs négatives → ValueError ---

    def test_negative_one_raises_value_error(self):
        with pytest.raises(ValueError):
            find_primes(-1)

    def test_negative_large_raises_value_error(self):
        with pytest.raises(ValueError):
            find_primes(-1000)

    def test_negative_min_int_raises_value_error(self):
        with pytest.raises(ValueError):
            find_primes(-(2**31))

    # --- Messages d'erreur ---

    def test_type_error_message_contains_type_name(self):
        """Le message TypeError doit mentionner le type reçu."""
        with pytest.raises(TypeError, match="float"):
            find_primes(5.5)

    def test_value_error_message_contains_value(self):
        """Le message ValueError doit mentionner la valeur reçue."""
        with pytest.raises(ValueError, match="-3"):
            find_primes(-3)

    # --- Valeurs limites valides ---

    def test_large_n_returns_correct_count(self):
        """find_primes(10_000) doit retourner exactement 10 000 éléments."""
        result = find_primes(10_000)
        assert len(result) == 10_000

    def test_large_n_last_prime(self):
        """Le 10 000e nombre premier doit être 104 729."""
        result = find_primes(10_000)
        assert result[-1] == 104_729, f"10 000e premier attendu: 104729, obtenu: {result[-1]}"

    def test_very_large_n_returns_correct_count(self):
        """find_primes(100_000) doit retourner exactement 100 000 éléments."""
        result = find_primes(100_000)
        assert len(result) == 100_000

    def test_very_large_n_last_prime(self):
        """Le 100 000e nombre premier doit être 1 299 709."""
        result = find_primes(100_000)
        assert result[-1] == 1_299_709, f"100 000e premier attendu: 1299709, obtenu: {result[-1]}"

    def test_n_equals_6_boundary(self):
        """n=6 est la frontière de la formule _upper_bound ; doit fonctionner."""
        result = find_primes(6)
        assert result == [2, 3, 5, 7, 11, 13]

    def test_n_equals_5_boundary(self):
        """n=5 utilise la borne fixe ; doit fonctionner."""
        result = find_primes(5)
        assert result == [2, 3, 5, 7, 11]


# ===========================================================================
# Classe 3 — Performance
# ===========================================================================

class TestPerformance:
    """Mesure les temps d'exécution et vérifie qu'ils restent raisonnables."""

    # Seuils de temps (secondes) — généreux pour des CI/machines lentes.
    TIME_LIMITS = {
        100:     0.1,    # 100 premiers    : < 100 ms
        1_000:   0.2,    # 1 000 premiers  : < 200 ms
        10_000:  1.0,    # 10 000 premiers : < 1 s
        100_000: 5.0,    # 100 000 premiers: < 5 s
    }

    @pytest.mark.parametrize("n", [100, 1_000, 10_000, 100_000])
    def test_performance(self, n, record_property):
        """Mesure et enregistre le temps d'exécution pour find_primes(n)."""
        start = time.perf_counter()
        result = find_primes(n)
        elapsed = time.perf_counter() - start

        # Enregistrement pour le rapport pytest (--junit-xml)
        record_property(f"duration_n{n}", round(elapsed, 6))
        record_property(f"result_count_n{n}", len(result))

        limit = self.TIME_LIMITS[n]
        assert elapsed < limit, (
            f"find_primes({n}) trop lent : {elapsed:.4f}s > seuil {limit}s"
        )
        assert len(result) == n, f"Résultat incorrect pour n={n}"

    @pytest.mark.skipif(not HAS_BENCHMARK, reason="pytest-benchmark non installé")
    def test_performance_100(self, benchmark):
        """Benchmark précis pour N=100 avec pytest-benchmark (si disponible)."""
        benchmark(find_primes, 100)

    def test_idempotency_performance(self):
        """Deux appels successifs à find_primes(1000) doivent donner le même résultat."""
        r1 = find_primes(1_000)
        r2 = find_primes(1_000)
        assert r1 == r2

    @pytest.mark.parametrize("n", [100, 1_000, 10_000, 100_000])
    def test_timing_reported(self, n, capsys):
        """Affiche les timings pour faciliter le reporting (toujours réussi)."""
        start = time.perf_counter()
        find_primes(n)
        elapsed = time.perf_counter() - start
        print(f"\n[PERF] find_primes({n:>7}) -> {elapsed:.6f}s")
        assert True  # Ce test ne peut pas échouer — il sert de rapport


# ===========================================================================
# Classe 4 — Fonctions internes (_sieve, _upper_bound)
# ===========================================================================

class TestInternals:
    """Tests des fonctions privées pour un meilleur diagnostic."""

    def test_sieve_below_two(self):
        """_sieve sur une borne < 2 doit retourner une liste vide."""
        assert _sieve(0) == []
        assert _sieve(1) == []

    def test_sieve_exact_prime(self):
        """_sieve(10) doit contenir exactement [2, 3, 5, 7]."""
        assert _sieve(10) == [2, 3, 5, 7]

    def test_sieve_exact_composite(self):
        """_sieve(8) ne doit pas inclure 4, 6, 8."""
        result = _sieve(8)
        assert 4 not in result
        assert 6 not in result
        assert 8 not in result

    def test_sieve_includes_limit_if_prime(self):
        """_sieve(13) doit inclure 13 (borne incluse)."""
        assert 13 in _sieve(13)

    def test_upper_bound_small_n(self):
        """Pour n < 6, la borne doit être 15."""
        for n in range(1, 6):
            assert _upper_bound(n) == 15

    def test_upper_bound_strictly_above_nth_prime(self):
        """_upper_bound(n) doit être strictement supérieur au n-ième premier."""
        known = {
            6: 13, 10: 29, 20: 71, 50: 229, 100: 541, 1000: 7919
        }
        for n, pn in known.items():
            bound = _upper_bound(n)
            assert bound > pn, f"_upper_bound({n})={bound} n'est pas > p({n})={pn}"

    def test_upper_bound_grows_with_n(self):
        """_upper_bound doit être croissant en n pour des valeurs suffisamment grandes."""
        bounds = [_upper_bound(n) for n in range(6, 1001, 10)]
        assert bounds == sorted(bounds), "La borne supérieure n'est pas monotone."


# ===========================================================================
# Utilitaires locaux
# ===========================================================================

def _is_prime_naive(n: int) -> bool:
    """Teste la primalité par force brute (référence indépendante)."""
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, math.isqrt(n) + 1, 2):
        if n % i == 0:
            return False
    return True
