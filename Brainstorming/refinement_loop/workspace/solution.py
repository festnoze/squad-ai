"""
Module de recherche des nombres premiers.

Expose `find_primes(n)` qui retourne les n premiers nombres premiers,
en s'appuyant sur le crible d'Ératosthène et une estimation analytique
de la borne supérieure issue du théorème des nombres premiers.
"""

import math


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def find_primes(n: int) -> list[int]:
    """
    Retourne les n premiers nombres premiers dans l'ordre croissant.

    Stratégie :
        1. Estimer une borne supérieure ``limit`` telle que le n-ième premier
           soit inférieur à ``limit`` (formule de Rosser & Schoenfeld).
        2. Appliquer le crible d'Ératosthène jusqu'à ``limit``.
        3. Si l'estimation s'avère insuffisante (cas très rares pour n < 6),
           doubler la borne et recommencer.

    Complexité (dominée par le crible) :
        - Temps  : O(limit · log log limit)
        - Espace : O(limit)

    Args:
        n: Nombre de premiers à retourner. Doit être un entier >= 0.

    Returns:
        Liste des ``n`` premiers nombres premiers.
        Retourne une liste vide si ``n == 0``.

    Raises:
        TypeError:  Si ``n`` n'est pas un entier.
        ValueError: Si ``n`` est strictement négatif.

    Examples:
        >>> find_primes(0)
        []
        >>> find_primes(1)
        [2]
        >>> find_primes(10)
        [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    """
    if not isinstance(n, int):
        raise TypeError(f"n doit être un entier, reçu : {type(n).__name__!r}")
    if n < 0:
        raise ValueError(f"n doit être >= 0, reçu : {n}")
    if n == 0:
        return []

    limit = _upper_bound(n)

    # Boucle de sécurité : en pratique, une seule itération suffit toujours.
    while True:
        primes = _sieve(limit)
        if len(primes) >= n:
            return primes[:n]
        limit *= 2  # doublement de la borne (garde-fou théorique)


# ---------------------------------------------------------------------------
# Fonctions internes
# ---------------------------------------------------------------------------

def _upper_bound(n: int) -> int:
    """
    Calcule une borne supérieure garantie pour le n-ième nombre premier.

    Pour n >= 6, utilise l'inégalité de Rosser & Schoenfeld :
        p(n) < n · (ln n + ln ln n)

    Une marge de 5 % est ajoutée pour absorber les imprécisions aux petites
    valeurs de n. Pour n < 6, une borne fixe de 15 est renvoyée (elle couvre
    les six premiers premiers : 2, 3, 5, 7, 11, 13).

    Args:
        n: Rang du premier recherché (entier >= 1).

    Returns:
        Entier strictement supérieur au n-ième nombre premier.
    """
    if n < 6:
        return 15

    ln_n = math.log(n)
    ln_ln_n = math.log(ln_n)
    return int(n * (ln_n + ln_ln_n) * 1.05) + 3


def _sieve(limit: int) -> list[int]:
    """
    Applique le crible d'Ératosthène et retourne tous les premiers <= limit.

    Optimisations :
        - Utilisation d'un ``bytearray`` (1 octet/case) plutôt qu'une liste
          de booléens Python pour réduire l'empreinte mémoire.
        - Élimination des multiples démarrée à i² (les multiples inférieurs
          ont déjà été traités lors des itérations précédentes).
        - Itération externe limitée à ⌊√limit⌋.

    Args:
        limit: Borne supérieure du crible (incluse).

    Returns:
        Liste triée de tous les entiers premiers compris entre 2 et ``limit``.
    """
    if limit < 2:
        return []

    # is_prime[i] == 1  <=>  i est (encore) candidat premier
    is_prime = bytearray([1]) * (limit + 1)
    is_prime[0] = 0
    is_prime[1] = 0

    for i in range(2, math.isqrt(limit) + 1):
        if is_prime[i]:
            # Barre tous les multiples de i à partir de i²
            step = i
            start = i * i
            is_prime[start::step] = bytearray(len(is_prime[start::step]))

    return [i for i, flag in enumerate(is_prime) if flag]
