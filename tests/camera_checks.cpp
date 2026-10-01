#include <cassert>
#include <cmath>
#include <cstdio>
#include "facility_camera.h"
int main(){
 float origin[3]={0,100,0}, delta[3]={650,100,0};
 SM64Surface wall={0,0,0,{{300,-1000,-1000},{300,1000,-1000},{300,0,1000}}};
 assert(fabsf(facility_camera_ray(origin,delta,&wall,1)-300.f/650.f)<1e-5f);
 SM64Surface reversed=wall;for(int k=0;k<3;k++){reversed.vertices[0][k]=wall.vertices[2][k];reversed.vertices[2][k]=wall.vertices[0][k];}
 assert(fabsf(facility_camera_ray(origin,delta,&reversed,1)-300.f/650.f)<1e-5f);
 wall.vertices[0][0]=wall.vertices[1][0]=wall.vertices[2][0]=-300;
 assert(facility_camera_ray(origin,delta,&wall,1)==1);
 wall.vertices[0][0]=wall.vertices[1][0]=wall.vertices[2][0]=900;
 assert(facility_camera_ray(origin,delta,&wall,1)==1);
 wall.vertices[0][0]=wall.vertices[1][0]=wall.vertices[2][0]=300;
 float position[3]={0,0,0},eye[3];FacilityCamera camera={};
 facility_camera_update(&camera,position,0,1.f/60,eye,nullptr,0);
 assert(fabsf(eye[0]-650)<1e-5&&fabsf(eye[1]-200)<1e-5);
 facility_camera_update(&camera,position,0,1.f/60,eye,&wall,1);
 assert(eye[0]<280&&eye[0]>270); // 24 units before the wall along the ray.
 float inward=camera.fraction;
 facility_camera_update(&camera,position,0,1.f/60,eye,nullptr,0);
 assert(camera.fraction>inward&&camera.fraction<1);
 for(int i=0;i<400;i++)facility_camera_update(&camera,position,0,1.f/60,eye,nullptr,0);
 assert(fabsf(camera.fraction-1)<1e-5);
 facility_camera_update(&camera,position,0,1.f/60,eye,&wall,1);
 assert(eye[0]<280);
 puts("Camera wall, winding, distance, and smoothing checks passed.");
}
