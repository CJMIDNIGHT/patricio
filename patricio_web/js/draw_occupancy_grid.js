function draw_occupancy_grid(canvas, map_data, robotPosition) {

    var ctx = canvas.getContext("2d");
    //document.querySelector('canvas'); //canvas.getContext("2d");

    var map = map_data;
    var pointSize = 1;

    canvas.width = map.info.width;
    canvas.height = map.info.height;

    for (let i = 0; i < map.info.height; i++) {
        for (let j = 0; j < map.info.width; j++) {

            let posX = j;
            let posY = i;
            let pos = map.info.width * i + j;

            let gridValue = map.data[pos];

            var color = evaluarGradiente(gridValue);

            ctx.beginPath();
            ctx.fillRect(posX, posY, pointSize, pointSize);
            ctx.fillStyle = color;
            ctx.stroke();
        }
    }

    if(robotPosition) {
        let robotSize = {
            width:4,
            height:4,
        }
        let posX = robotPosition.x + canvas.width/2 - robotSize.width/2;
        let posY = robotPosition.y + canvas.height/2 - robotSize.height/2;

        // console.log(posX, posY)

        // ctx.beginPath();
        // ctx.fillStyle = 'green';
        // ctx.fillRect(posX, posY, robotSize.width, robotSize.height);
        // ctx.stroke();

        ctx.beginPath();
        ctx.fillStyle = 'green';
        ctx.arc(posX, posY, robotSize.width/2, 0, 2 * Math.PI);
        ctx.fill();
    }

}

function evaluarGradiente(valor) {

    if (valor == 100) return "rgb(0,0,0)"
    else if (valor == 0) return "rgb(255,255,255)"
    else if (valor < 0) return "rgb(120,120,120)"

    // Define la escala de colores
    var colores = [
        [0, 0, 0],
        [0, 0, 0],
        [255, 0, 255],
        [250, 0, 0],
        [0, 255, 255],
    ];

    // Convierte el valor en una posición en la escala
    var posicion = valor / 100 * (colores.length - 1);
    var posicionEntera = Math.floor(posicion);
    var posicionDecimal = posicion - posicionEntera;

    // Interpola entre los colores en las posiciones correspondientes
    var color1 = colores[posicionEntera];
    var color2 = colores[posicionEntera + 1];

    if (typeof color1 !== 'undefined' && typeof color2 !== 'undefined' && color1.length > 0 && color2.length > 0) {
        var r = color1[0] * (1 - posicionDecimal) + color2[0] * posicionDecimal;
        var g = color1[1] * (1 - posicionDecimal) + color2[1] * posicionDecimal;
        var b = color1[2] * (1 - posicionDecimal) + color2[2] * posicionDecimal;
    }

    // Devuelve el color en formato RGB
    return "rgb(" + Math.round(r) + ", " + Math.round(g) + ", " + Math.round(b) + ")";
}