# Environment textures

Color images in this folder are material sources for the game's environments and props. Their suggested roles correspond to the surface categories in `TextureLibrary`. Actual usage is determined by the game's materials and texture library, not by the presence of a file here.

| Image | Intended role |
| --- | --- |
| `grass.png` | Garden and outdoor lawn. |
| `soil.png` | Exposed earth, such as soil in plant pots. |
| `foliage.png` | Leaves and greenery on decorative plants. |
| `plaster.png` | Painted plaster on walls and related interior surfaces. |
| `crepi_cream_source.png` | Cream stucco with pronounced grain, an alternative wall color source. |
| `parquet.png` | Wooden plank floors and raised wooden flooring. |
| `tile.png` | Ceramic floor tiles, especially kitchens and bathrooms. |
| `carpet.png` | Carpeted floors, rugs and mats. |
| `wood.png` | Furniture, doors, shelves, frames and wooden trim. |
| `lacquer.png` | Painted or lacquered furniture surfaces. |
| `upholstery.png` | Fabric on sofas, armchairs, cushions and other padded seats. |
| `linen.png` | Fine fabric for lampshades, textiles and clothing. |
| `metal.png` | Neutral metal parts such as lamp poles, bases and chair frames. |
| `plastic.png` | Matte plastic on small props and furniture details. |
| `red_metal_source.png` | Vivid red painted-metal color source for the movable chair or other player-controlled furniture. |

The source images were generated with repeatable surfaces in mind. Opposite edges are not guaranteed to match; inspect and correct seams before tiling, especially on `tile.png`. The red source also requires a tiling check. Color images are not substitutes for the linear grayscale detail maps currently expected by the game.

`Detail/` contains separate grayscale detail maps and, for selected surfaces, normal maps. A detail map modulates the material color; a normal map supplies apparent surface relief. These files can differ from the color sources above and should be checked in the texture library before use.

For shiny red painted metal, the red image supplies base color only. Set smoothness and metallic properties in the material and use appropriate lighting and reflection sources for moving highlights. Metallic red paint and glossy red lacquer are different finishes; the latter generally uses a low metallic value.
