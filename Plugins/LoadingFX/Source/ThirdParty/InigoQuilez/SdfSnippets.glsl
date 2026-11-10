// Code snippets by Inigo Quilez, copied as published on https://iquilezles.org.
// The site states: "all technical code snippets you'll find are under the MIT
// license so you can easily reuse them". The pages give no year with it.
//
// This file is not compiled or loaded by the plugin. The LoadingFX materials
// re-implement these functions as material node graphs; README.txt in this
// folder lists which asset uses which function.
//
// The MIT License
// Copyright (c) Inigo Quilez
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.


// ---------------------------------------------------------------------------
// From "2D distance functions": https://iquilezles.org/articles/distfunctions2d/
// ---------------------------------------------------------------------------

// Arc - exact
// https://www.shadertoy.com/view/wl23RK
float sdArc( in vec2 p, in vec2 sc, in float ra, float rb )
{
    // sc is the sin/cos of the arc's aperture
    p.x = abs(p.x);
    return ((sc.y*p.x>sc.x*p.y) ? length(p-sc*ra) :
                                  abs(length(p)-ra)) - rb;
}

// Pie - exact
// https://www.shadertoy.com/view/3l23RK
float sdPie( in vec2 p, in vec2 c, in float r )
{
    p.x = abs(p.x);
    float l = length(p) - r;
    float m = length(p-c*clamp(dot(p,c),0.0,r)); // c=sin/cos of aperture
    return max(l,m*sign(c.y*p.x-c.x*p.y));
}

// Segment - exact
// https://www.shadertoy.com/view/3tdSDj
float sdSegment( in vec2 p, in vec2 a, in vec2 b )
{
    vec2 pa = p-a, ba = b-a;
    float h = clamp( dot(pa,ba)/dot(ba,ba), 0.0, 1.0 );
    return length( pa - ba*h );
}


// ---------------------------------------------------------------------------
// From "3D distance functions": https://iquilezles.org/articles/distfunctions/
// LoadingFX uses these two in 2D (vec2 instead of vec3).
// ---------------------------------------------------------------------------

// Round Box
float sdRoundBox( vec3 p, vec3 b, float r )
{
  vec3 q = abs(p) - b + r;
  return length(max(q,0.0)) + min(max(q.x,max(q.y,q.z)),0.0) - r;
}

// Ellipsoid - lower bound
// https://www.shadertoy.com/view/tdS3DG
float sdEllipsoid( vec3 p, vec3 r )
{
  float k0 = length(p/r);
  float k1 = length(p/(r*r));
  return k0*(k0-1.0)/k1;
}


// ---------------------------------------------------------------------------
// From "smooth minimum": https://iquilezles.org/articles/smin/
// ---------------------------------------------------------------------------

// quadratic polynomial
float smin( float a, float b, float k )
{
    k *= 4.0;
    float h = max( k-abs(a-b), 0.0 )/k;
    return min(a,b) - h*h*k*(1.0/4.0);
}
