import pytest

class TestLeetCode:
    @pytest.mark.parametrize("nums, target, awaited_result", [
        ([2, 7, 11, 15], 9, [0, 1]), # Basic case with positive integers
        ([3, 2, 4], 6, [1, 2]), # Case with positive integers and different order
        ([3, 3], 6, [0, 1]), # Case with duplicates
        ([1, 2, 3, 4], 5, [0, 3]), # Case with larger numbers
        ([1, -1, -2, -3], -3, [1, 2]), # Case with negative numbers
        ([1.5, 2.5, 3.5], 4.0, [0, 1]), # Case with floats
        ([1000000000, 2000000000], 3000000000, [0, 1]), # Case with large numbers
    ])
    def test_twoSum(self, nums: list[int], target: int, awaited_result:list[int]) -> list[int]:
        result = TestLeetCode.twoSum(nums, target)
        assert result == awaited_result

    def twoSum(nums: list[int], target: int) -> list[int]:
        first_index = 0
        while first_index < len(nums):
            for i in range(len(nums)):
                if i == first_index:
                    continue
                if nums[first_index] + nums[i] == target:
                    return [first_index, i]
            first_index += 1
        return []
    
    @pytest.mark.parametrize("dividend, divisor, awaited_res", [
        (10, 3, 3), # Basic case
        (7, -3, -2), # Negative divisor
        (-7, 3, -2), # Negative dividend
        (-10, -3, 3), # Both negative
        (-1, 1, -1), 
        (1000000, 3, 333333), # Large numbers
        (2**31, 1, 2**31 - 1), # Edge case for max int + 1
        (2**32 + 7, -1, -(2**31 - 1)), # Edge case for negative result
    ])
    def test_divide(self, dividend: int, divisor: int, awaited_res: int) -> int:
        result = TestLeetCode.divide(dividend, divisor)
        assert result == awaited_res

    def divide(dividend: int, divisor: int) -> int:
        if divisor == 0:
            raise ValueError("Division by zero is not allowed.")
        is_negative = (dividend < 0 or divisor < 0) and not (dividend < 0 and divisor < 0)
        dividend = abs(dividend)
        divisor = abs(divisor)
        remain = dividend
        result = 0

        if divisor == 1:
            if dividend > (2**31 - 1): dividend = (2**31 - 1)
            return dividend if not is_negative else -dividend

        while True:
            if remain >= divisor and result < (2**31 - 1):
                remain -= divisor
                result += 1
            else:
                if result > (2**31 - 1): result = (2**31 - 1)
                return result if not is_negative else -result