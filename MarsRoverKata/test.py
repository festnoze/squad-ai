import pytest
from main import Plateau, Rover, MarsRoverMission


class TestPlateau:
    def test_init(self):
        """Test Plateau initialization."""
        plateau = Plateau(5, 5)
        assert plateau.width == 5
        assert plateau.height == 5

    @pytest.mark.parametrize("x, y, expected", [
        # Valid positions
        (0, 0, True),   # Origin
        (5, 5, True),   # Upper right corner
        (3, 2, True),   # Middle
        # Invalid positions
        (-1, 0, False),  # Out of bounds (negative x)
        (0, -1, False),  # Out of bounds (negative y)
        (6, 5, False),   # Out of bounds (x too large)
        (5, 6, False),   # Out of bounds (y too large)
    ])
    def test_is_valid_position(self, x, y, expected):
        """Test position validation with multiple coordinates."""
        plateau = Plateau(5, 5)
        assert plateau.is_valid_position(x, y) == expected


class TestRover:
    def test_init(self):
        """Test Rover initialization."""
        plateau = Plateau(5, 5)
        rover = Rover(1, 2, 'N', plateau)
        
        assert rover.x == 1
        assert rover.y == 2
        assert rover.direction == 'N'
        assert rover.plateau == plateau

    @pytest.mark.parametrize("initial_direction, expected_direction", [
        ('N', 'W'),
        ('E', 'N'),
        ('S', 'E'),
        ('W', 'S'),
    ])
    def test_turn_left(self, initial_direction, expected_direction):
        """Test turning left from all directions."""
        plateau = Plateau(5, 5)
        rover = Rover(0, 0, initial_direction, plateau)
        rover.turn_left()
        assert rover.direction == expected_direction

    @pytest.mark.parametrize("initial_direction, expected_direction", [
        ('N', 'E'),
        ('E', 'S'),
        ('S', 'W'),
        ('W', 'N'),
    ])
    def test_turn_right(self, initial_direction, expected_direction):
        """Test turning right from all directions."""
        plateau = Plateau(5, 5)
        rover = Rover(0, 0, initial_direction, plateau)
        rover.turn_right()
        assert rover.direction == expected_direction

    @pytest.mark.parametrize("direction, expected_x, expected_y", [
        ('N', 2, 3),  # North: y increases
        ('E', 3, 2),  # East: x increases
        ('S', 2, 1),  # South: y decreases
        ('W', 1, 2),  # West: x decreases
    ])
    def test_move(self, direction, expected_x, expected_y):
        """Test moving in each direction."""
        plateau = Plateau(5, 5)
        rover = Rover(2, 2, direction, plateau)
        rover.move()
        assert rover.x == expected_x
        assert rover.y == expected_y

    @pytest.mark.parametrize("x, y, direction, expected_x, expected_y", [
        # Boundary cases where rover should not move
        (2, 5, 'N', 2, 5),  # North boundary
        (5, 2, 'E', 5, 2),  # East boundary
        (2, 0, 'S', 2, 0),  # South boundary
        (0, 2, 'W', 0, 2),  # West boundary
    ])
    def test_move_boundary(self, x, y, direction, expected_x, expected_y):
        """Test movement at boundaries."""
        plateau = Plateau(5, 5)
        rover = Rover(x, y, direction, plateau)
        rover.move()
        assert rover.x == expected_x
        assert rover.y == expected_y

    @pytest.mark.parametrize("command, expected_x, expected_y, expected_direction", [
        ('L', 1, 2, 'W'),  # Turn left
        ('R', 1, 2, 'E'),  # Turn right
        ('M', 1, 3, 'N'),  # Move forward
    ])
    def test_execute_command(self, command, expected_x, expected_y, expected_direction):
        """Test executing individual commands."""
        plateau = Plateau(5, 5)
        rover = Rover(1, 2, 'N', plateau)
        rover.execute_command(command)
        assert rover.x == expected_x
        assert rover.y == expected_y
        assert rover.direction == expected_direction

    @pytest.mark.parametrize("initial_x, initial_y, initial_direction, commands, expected_x, expected_y, expected_direction", [
        (1, 2, 'N', 'LMLMLMLMM', 1, 3, 'N'),  # Example case 1
        (3, 3, 'E', 'MMRMMRMRRM', 5, 1, 'E'),  # Example case 2
        (0, 0, 'N', 'RM', 1, 0, 'E'),  # Simple case: turn right and move
        (2, 2, 'W', 'MLMLM', 2, 1, 'E'),  # Move west, turn south, move south, turn east, move east
    ])
    def test_execute_commands(self, initial_x, initial_y, initial_direction, commands, expected_x, expected_y, expected_direction):
        """Test executing sequences of commands."""
        plateau = Plateau(5, 5)
        rover = Rover(initial_x, initial_y, initial_direction, plateau)
        rover.execute_commands(commands)
        assert rover.x == expected_x
        assert rover.y == expected_y
        assert rover.direction == expected_direction

    def test_get_position(self):
        """Test getting position string."""
        plateau = Plateau(5, 5)
        rover = Rover(1, 2, 'N', plateau)
        
        assert rover.get_position() == "1 2 N"


class TestMarsRoverMission:
    def test_init(self):
        """Test MarsRoverMission initialization."""
        mission = MarsRoverMission()
        
        assert mission.plateau is None
        assert mission.rovers == []
        assert mission.commands == []

    @pytest.mark.parametrize("input_text, expected_plateau, expected_rovers, expected_commands", [
        (
            """5 5
1 2 N
LMLMLMLMM
3 3 E
MMRMMRMRRM""",
            (5, 5),  # (width, height)
            [(1, 2, 'N'), (3, 3, 'E')],  # [(x, y, direction), ...]
            ['LMLMLMLMM', 'MMRMMRMRRM']  # [commands, ...]
        ),
        (
            """3 4
0 0 N
MRM
2 2 S
LMLM""",
            (3, 4),
            [(0, 0, 'N'), (2, 2, 'S')],
            ['MRM', 'LMLM']
        ),
    ])
    def test_parse_input(self, input_text, expected_plateau, expected_rovers, expected_commands):
        """Test parsing mission input with different input formats."""
        mission = MarsRoverMission()
        mission.parse_input(input_text)
        
        # Check plateau was created correctly
        assert mission.plateau.width == expected_plateau[0]
        assert mission.plateau.height == expected_plateau[1]
        
        # Check rovers were created correctly
        assert len(mission.rovers) == len(expected_rovers)
        for i, (x, y, direction) in enumerate(expected_rovers):
            assert mission.rovers[i].x == x
            assert mission.rovers[i].y == y
            assert mission.rovers[i].direction == direction
        
        # Check commands were stored correctly
        assert mission.commands == expected_commands

    @pytest.mark.parametrize("input_text, expected_results, expected_positions", [
        (
            """5 5
1 2 N
LMLMLMLMM
3 3 E
MMRMMRMRRM""",
            ["1 3 N", "5 1 E"],
            [(1, 3, 'N'), (5, 1, 'E')]
        ),
        (
            """3 4
0 0 N
MRM
2 2 S
LMLM""",
            ["1 1 E", "3 3 N"],
            [(1, 1, 'E'), (3, 3, 'N')]
        ),
    ])
    def test_run_mission(self, input_text, expected_results, expected_positions):
        """Test running the mission with different input scenarios."""
        mission = MarsRoverMission()
        mission.parse_input(input_text)
        results = mission.run_mission()
        
        # Check expected results
        assert results == expected_results
        
        # Verify rover positions directly
        for i, (x, y, direction) in enumerate(expected_positions):
            assert mission.rovers[i].x == x
            assert mission.rovers[i].y == y
            assert mission.rovers[i].direction == direction

    @pytest.mark.parametrize("input_text, expected_rover_count", [
        ("""5 5

1 2 N

LMLMLMLMM

3 3 E
MMRMMRMRRM
""", 2),
        ("""5 5
1 2 N

LMLMLMLMM


3 3 E

MMRMMRMRRM
""", 2),
        ("""5 5


1 2 N
LMLMLMLMM
""", 1),
    ])
    def test_parse_input_with_empty_lines(self, input_text, expected_rover_count):
        """Test parsing with empty lines in input."""
        mission = MarsRoverMission()
        mission.parse_input(input_text)
        
        # Should handle empty lines correctly
        assert len(mission.rovers) == expected_rover_count
        assert len(mission.commands) == expected_rover_count


@pytest.mark.parametrize("input_text, expected_results", [
    (
        """5 5
1 2 N
LMLMLMLMM
3 3 E
MMRMMRMRRM""",
        ["1 3 N", "5 1 E"]
    ),
    (
        """3 3
0 0 N
MMM
1 1 E
MMM""",
        ["0 3 N", "3 1 E"]
    ),
])
def test_example_cases(input_text, expected_results):
    """Test multiple example cases."""
    mission = MarsRoverMission()
    mission.parse_input(input_text)
    results = mission.run_mission()
    
    assert results == expected_results


if __name__ == "__main__":
    pytest.main()
