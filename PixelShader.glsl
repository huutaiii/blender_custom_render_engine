
in vec4 color;
in vec3 normal;
in float outline;

uniform mat4 directional_lights;
const float sharpness = 0.99;

void main()
{
    if (outline > 0)
    {
        gl_FragColor = vec4(0, 0, 0, 1);
    } 
    else
    {
        vec4 base_color = color;
        gl_FragColor = base_color * 0.1;
        for (int i = 0; i <= 3; ++i)
        {
            vec3 light = directional_lights[i].xyz;
            float nl = smoothstep(0, 1 - sharpness, dot(normal, light));
            gl_FragColor.xyz += base_color.xyz * nl;
        }
    }
}
