import pygame
import bomberman_engine as bme

class KeyboardController:
    def __init__(self):
        pass

    def get_command(self) -> bme.Command:
        keys = pygame.key.get_pressed()
        
        # Bomb placement
        if keys[pygame.K_SPACE]:
            return bme.Command.PLACE_BOMB
            
        # Movement
        if keys[pygame.K_UP]:
            return bme.Command.UP
        elif keys[pygame.K_DOWN]:
            return bme.Command.DOWN
        elif keys[pygame.K_LEFT]:
            return bme.Command.LEFT
        elif keys[pygame.K_RIGHT]:
            return bme.Command.RIGHT
            
        # Default if nothing is pressed
        return bme.Command.NONE