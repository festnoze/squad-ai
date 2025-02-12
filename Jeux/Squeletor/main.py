import pygame

# Level design large, description explicite
level_data: dict = {
    "level_1": [
        "................................................................................",
        "................................................................................",
        "..P..................###........................................................",
        "..................###............................................................",
        ".............###...........###................###...............................",
        "................................................................................",
        "................................................................................",
        "..................###............................................................",
        "..........###....................................................###............",
        "............................................###..................................",
        "..............###...........................................###.................",
        ".......###........###............................................................",
        "................................##...............................................",
        "........................###......................................................",
        "............................###..................................................",
        "................................................................................",
    ]
}

zoom_level = 2
base_tile_size = 32
tile_size = base_tile_size * zoom_level
screen_width: int = 1600
screen_height: int = 960

player_image_path: str = "media/player-right.webp"
block_image_path: str = "media/ground-tile.png"
background_image_path: str = "media/background.png"
top_block_path = "media/ground-tile.png"
bottom_block_path = "media/ground-tile.png"
wall_block_path = "media/ground-tile.png"

class Player(pygame.sprite.Sprite):
    def __init__(self, image_path: str, x: int, y: int, tile_size: int) -> None:
        super().__init__()
        original_image = pygame.image.load(image_path).convert_alpha()
        rect = original_image.get_rect()
        ratio = min(tile_size / rect.width, tile_size / rect.height)
        new_width = int(rect.width * ratio)
        new_height = int(rect.height * ratio)
        self.image = pygame.transform.scale(original_image, (new_width, new_height))
        self.rect = self.image.get_rect()
        self.rect.x = x
        self.rect.y = y
        self.speed_x = 0
        self.speed_y = 0

class Block(pygame.sprite.Sprite):
    def __init__(self, image: pygame.Surface, x: int, y: int) -> None:
        super().__init__()
        self.image = image.copy()
        self.rect = self.image.get_rect()
        self.rect.x = x
        self.rect.y = y

class PlatformerGame:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        self.clock = pygame.time.Clock()
        self.current_level = level_data["level_1"]
        # On agrandit la hauteur totale pour qu'on puisse voir la rangée du sol
        self.world_width = len(self.current_level[0]) * tile_size
        self.world_height = (len(self.current_level)+1) * tile_size
        self.gravity = 0.3 * zoom_level
        self.jump_power = -10.0 * zoom_level
        self.offset_x = 0
        self.offset_y = 0
        self.background_offset_x = 0.0
        self.background_offset_y = 0.0

        try:
            bg = pygame.image.load(background_image_path)
            self.background_image = bg
            # ratio = screen_height / bg.get_height()
            # self.background_image = pygame.transform.scale(bg, bg.get_width() * ratio, bg.get_height() * ratio).convert_alpha()
        except:
            self.background_image = None

        orig_block = pygame.image.load(block_image_path).convert_alpha()
        self.block_image = pygame.transform.scale(orig_block, (tile_size, tile_size))

        self.top_block_image = pygame.transform.scale(pygame.image.load(top_block_path).convert_alpha(), (tile_size, tile_size))
        self.bottom_block_image = pygame.transform.scale(pygame.image.load(bottom_block_path).convert_alpha(), (tile_size, tile_size))
        self.wall_block_image = pygame.transform.scale(pygame.image.load(wall_block_path).convert_alpha(), (tile_size, tile_size))

        self.block_group = pygame.sprite.Group()
        self.tiles = []
        player_x = 0
        player_y = 0
        for row_index, row in enumerate(self.current_level):
            for col_index, col in enumerate(row):
                if col == '#':
                    self.tiles.append(pygame.Rect(col_index * tile_size, row_index * tile_size, tile_size, tile_size))
                    block = Block(self.block_image, col_index * tile_size, row_index * tile_size)
                    self.block_group.add(block)
                elif col == 'P':
                    player_x = col_index * tile_size
                    player_y = row_index * tile_size
        self.add_bounding_blocks()
        self.player = Player(player_image_path, player_x, player_y, tile_size)

    def add_bounding_blocks(self) -> None:
        # Plafond et sol : on place le sol un rang sous le niveau
        for col_index in range(len(self.current_level[0]) + 2):
            top_block_rect = pygame.Rect((col_index - 1) * tile_size, 0 - tile_size, tile_size, tile_size)
            bottom_block_rect = pygame.Rect((col_index - 1) * tile_size, len(self.current_level) * tile_size, tile_size, tile_size)
            self.tiles.append(top_block_rect)
            self.tiles.append(bottom_block_rect)
            tb = Block(self.top_block_image, top_block_rect.x, top_block_rect.y)
            bb = Block(self.bottom_block_image, bottom_block_rect.x, bottom_block_rect.y)
            self.block_group.add(tb)
            self.block_group.add(bb)
        # Murs sur les côtés
        for row_index in range(len(self.current_level)+1):
            left_block_rect = pygame.Rect(-tile_size, row_index * tile_size - tile_size, tile_size, tile_size)
            right_block_rect = pygame.Rect(len(self.current_level[0]) * tile_size, row_index * tile_size - tile_size, tile_size, tile_size)
            self.tiles.append(left_block_rect)
            self.tiles.append(right_block_rect)
            lb = Block(self.wall_block_image, left_block_rect.x, left_block_rect.y)
            rb = Block(self.wall_block_image, right_block_rect.x, right_block_rect.y)
            self.block_group.add(lb)
            self.block_group.add(rb)

    def run_game(self) -> None:
        running = True
        while running:
            self.clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT:
                        self.player.speed_x = -4
                    elif event.key == pygame.K_RIGHT:
                        self.player.speed_x = 4
                    elif event.key == pygame.K_UP:
                        if self.check_floor():
                            self.player.speed_y = self.jump_power
                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_LEFT and self.player.speed_x < 0:
                        self.player.speed_x = 0
                    elif event.key == pygame.K_RIGHT and self.player.speed_x > 0:
                        self.player.speed_x = 0

            # Physique
            self.player.speed_y += self.gravity
            self.player.rect.y += self.player.speed_y
            block_hit_list = self.collision_checks(self.player.rect, 0, self.player.speed_y)
            for block in block_hit_list:
                if self.player.speed_y > 0:
                    self.player.rect.y = block.top - self.player.rect.height
                    self.player.speed_y = 0
                elif self.player.speed_y < 0:
                    self.player.rect.y = block.bottom
                    self.player.speed_y = 0

            self.player.rect.x += self.player.speed_x
            block_hit_list = self.collision_checks(self.player.rect, self.player.speed_x, 0)
            for block in block_hit_list:
                if self.player.speed_x > 0:
                    self.player.rect.x = block.left - self.player.rect.width
                elif self.player.speed_x < 0:
                    self.player.rect.x = block.right

            # Caméra horizontale
            if self.player.rect.x - self.offset_x > screen_width * 0.7:
                self.offset_x = self.player.rect.x - screen_width * 0.7
            elif self.player.rect.x - self.offset_x < screen_width * 0.3:
                self.offset_x = self.player.rect.x - screen_width * 0.3

            if self.offset_x < 0:
                self.offset_x = 0
            max_offset_x = self.world_width - screen_width
            if self.offset_x > max_offset_x:
                self.offset_x = max_offset_x

            # Caméra verticale
            if self.player.rect.y - self.offset_y > screen_height * 0.7:
                self.offset_y = self.player.rect.y - screen_height * 0.7
            elif self.player.rect.y - self.offset_y < screen_height * 0.3:
                self.offset_y = self.player.rect.y - screen_height * 0.3

            if self.offset_y < 0:
                self.offset_y = 0
            max_offset_y = self.world_height - screen_height
            if self.offset_y > max_offset_y:
                self.offset_y = max_offset_y

            self.background_offset_x = self.offset_x * 0.25
            self.background_offset_y = self.offset_y * 0.25

            # Arrière-plan
            if self.background_image:
                bg_w = self.background_image.get_width()
                bg_h = self.background_image.get_height()
                bg_x = int(-self.background_offset_x) % bg_w
                bg_y = int(-self.background_offset_y) % bg_h
                self.screen.fill((0, 0, 0))
                for x in range(-bg_w, screen_width + bg_w, bg_w):
                    for y in range(-bg_h, screen_height + bg_h, bg_h):
                        self.screen.blit(self.background_image, (x - bg_x, y - bg_y))
            else:
                self.screen.fill((100,150,200))

            # Affiche les blocs
            for block in self.block_group:
                draw_x = block.rect.x - self.offset_x
                draw_y = block.rect.y - self.offset_y
                if (draw_x + block.rect.width >= 0 and draw_x <= screen_width) and (draw_y + block.rect.height >= 0 and draw_y <= screen_height):
                    self.screen.blit(block.image, (draw_x, draw_y))

            # Affiche le joueur
            self.screen.blit(self.player.image, (self.player.rect.x - self.offset_x, self.player.rect.y - self.offset_y))

            pygame.display.flip()

        pygame.quit()
        return None

    def collision_checks(self, rect: pygame.Rect, x_speed: int, y_speed: float) -> list:
        hit_list = []
        for tile in self.tiles:
            if rect.colliderect(tile):
                hit_list.append(tile)
        return hit_list

    def check_floor(self) -> bool:
        test_rect = pygame.Rect(self.player.rect.x, self.player.rect.y + 1, self.player.rect.width, self.player.rect.height)
        for tile in self.tiles:
            if test_rect.colliderect(tile):
                return True
        return False

def main() -> None:
    game = PlatformerGame()
    game.run_game()

if __name__ == "__main__":
    main()
