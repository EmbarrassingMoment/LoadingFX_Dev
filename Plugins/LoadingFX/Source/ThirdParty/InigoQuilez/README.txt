Third-party code: snippets by Inigo Quilez (MIT)
================================================

SdfSnippets.glsl holds the code snippets by Inigo Quilez that LoadingFX is
based on, as published on https://iquilezles.org, with their MIT license.

The plugin does not compile or load this file. Each function below was
re-implemented as a material node graph in the plugin's Content folder.
Unreal Engine loads assets only from Content, so those assets stay there;
this folder holds the original code and its license.

Function (in SdfSnippets.glsl)      Assets that implement it (under Content/)
----------------------------------  -----------------------------------------
sdArc                               Materials/M_LoadingArc
                                    Materials/M_LoadingDualArc
                                    Materials/M_LoadingSegments
sdPie                               Materials/M_LoadingTimer
sdSegment                           MaterialFunctions/MF_SdSegment2D
                                      (used by Materials/M_LoadingHourglass)
sdRoundBox (in 2D)                  MaterialFunctions/MF_SdRoundBox2D
                                      (used by Materials/M_LoadingBoxes and
                                       Materials/M_LoadingMorph)
sdEllipsoid (in 2D, as an ellipse;  MaterialFunctions/MF_SdEllipse2D
  the center is clamped to avoid      (used by Materials/M_LoadingBounce)
  0 / 0)
smin (quadratic polynomial)         Materials/M_LoadingGooey
                                    Materials/M_LoadingChase

Sources:
  https://iquilezles.org/articles/distfunctions2d/
  https://iquilezles.org/articles/distfunctions/
  https://iquilezles.org/articles/smin/
