class Plateau:
    """
    Represents the rectangular plateau on Mars where rovers will navigate.
    Provides boundary checking for rover movement.
    """
    
    def __init__(self, width, height):
        """
        Initialize a plateau with given dimensions.
        
        Args:
            width (int): Width of the plateau (max x-coordinate)
            height (int): Height of the plateau (max y-coordinate)
        """
        self.width = width
        self.height = height
    
    def is_valid_position(self, x, y):
        """
        Check if the given position is within the plateau boundaries.
        
        Args:
            x (int): X-coordinate to check
            y (int): Y-coordinate to check
            
        Returns:
            bool: True if position is valid, False otherwise
        """
        return 0 <= x <= self.width and 0 <= y <= self.height


class Rover:
    """
    Represents a robotic rover on Mars.
    Capable of turning left/right and moving forward according to commands.
    """
    
    # Cardinal directions in clockwise order
    DIRECTIONS = ['N', 'E', 'S', 'W']
    
    # Movement deltas for each direction (N, E, S, W)
    MOVES = {
        'N': (0, 1),   # North: y increases by 1
        'E': (1, 0),   # East: x increases by 1
        'S': (0, -1),  # South: y decreases by 1
        'W': (-1, 0)   # West: x decreases by 1
    }
    
    def __init__(self, x, y, direction, plateau):
        """
        Initialize a rover with position, direction and plateau.
        
        Args:
            x (int): Initial x-coordinate
            y (int): Initial y-coordinate
            direction (str): Initial direction (N, E, S, W)
            plateau (Plateau): The plateau the rover is on
        """
        self.x = x
        self.y = y
        self.direction = direction
        self.plateau = plateau
    
    def turn_left(self):
        """Turn the rover 90 degrees to the left."""
        current_index = self.DIRECTIONS.index(self.direction)
        self.direction = self.DIRECTIONS[(current_index - 1) % 4]
    
    def turn_right(self):
        """Turn the rover 90 degrees to the right."""
        current_index = self.DIRECTIONS.index(self.direction)
        self.direction = self.DIRECTIONS[(current_index + 1) % 4]
    
    def move(self):
        """
        Move the rover one grid point in the direction it's facing.
        Only moves if the new position is valid.
        """
        dx, dy = self.MOVES[self.direction]
        new_x = self.x + dx
        new_y = self.y + dy
        
        if self.plateau.is_valid_position(new_x, new_y):
            self.x = new_x
            self.y = new_y
    
    def execute_command(self, command):
        """
        Execute a single command.
        
        Args:
            command (str): One of 'L', 'R', or 'M'
        """
        if command == 'L':
            self.turn_left()
        elif command == 'R':
            self.turn_right()
        elif command == 'M':
            self.move()
    
    def execute_commands(self, commands):
        """
        Execute a sequence of commands.
        
        Args:
            commands (str): String of commands ('L', 'R', 'M')
        """
        for command in commands:
            self.execute_command(command)
    
    def get_position(self):
        """
        Get the current position and direction of the rover.
        
        Returns:
            str: Position in format "x y direction"
        """
        return f"{self.x} {self.y} {self.direction}"


class MarsRoverMission:
    """
    Manages the overall Mars Rover mission.
    Handles input parsing, rover execution, and result output.
    """
    
    def __init__(self):
        """Initialize the Mars Rover mission."""
        self.plateau = None
        self.rovers = []
        self.commands = []
    
    def parse_input(self, input_text):
        """
        Parse the input text to set up the mission.
        
        Args:
            input_text (str): Multi-line input as described in the problem
        """
        lines = input_text.strip().split('\n')
        
        # Parse plateau dimensions
        plateau_coords = lines[0].split()
        width = int(plateau_coords[0])
        height = int(plateau_coords[1])
        self.plateau = Plateau(width, height)
        
        # Parse rover positions and commands
        i = 1
        while i < len(lines):
            if not lines[i].strip():  # Skip empty lines
                i += 1
                continue
                
            # Parse rover position
            position = lines[i].split()
            if len(position) == 3:
                x = int(position[0])
                y = int(position[1])
                direction = position[2]
                
                # Parse rover commands (next line)
                i += 1
                if i < len(lines):
                    commands = lines[i].strip()
                    
                    # Create rover and store commands
                    rover = Rover(x, y, direction, self.plateau)
                    self.rovers.append(rover)
                    self.commands.append(commands)
            
            i += 1
    
    def run_mission(self):
        """
        Run the mission by executing commands for each rover in sequence.
        
        Returns:
            list: Final positions of all rovers
        """
        results = []
        
        for i, rover in enumerate(self.rovers):
            rover.execute_commands(self.commands[i])
            results.append(rover.get_position())
        
        return results
    
    def print_results(self, results):
        """
        Print the results in the required format.
        
        Args:
            results (list): List of final rover positions
        """
        for result in results:
            print(result)
            
        # Return the results for verification
        return results


def main():
    """Main function to run the Mars Rover mission."""
    # Create a new mission
    mission = MarsRoverMission()
    
    # Process the input as specified in the problem statement
    sample_input = """5 5
1 2 N
LMLMLMLMM
3 3 E
MMRMMRMRRM"""
    
    # Parse the input, run the mission, and print the results
    mission.parse_input(sample_input)
    results = mission.run_mission()
    mission.print_results(results)


if __name__ == "__main__":
    main()
