package com.powerresfot.examenfinal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.stream.Collectors;

@RestController
public class DatosController {

    private static final DateTimeFormatter FECHA_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private static final DateTimeFormatter HORA_FMT = DateTimeFormatter.ofPattern("HH:mm:ss");

    private final InteraccionRepository repository;

    @Value("${server.name:server-default}")
    private String serverName;

    public DatosController(InteraccionRepository repository) {
        this.repository = repository;
    }

    @GetMapping(value = "/datos", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> getDatos() {
        List<Interaccion> interacciones = repository.findAllOrderedById();

        String datos = interacciones.stream()
                .map(i -> String.join(", ",
                        i.getUsuario(),
                        i.getAccion(),
                        i.getFecha().format(FECHA_FMT),
                        i.getHora().format(HORA_FMT),
                        i.getVideo()))
                .collect(Collectors.joining("\n"));

        String encabezado = "### Peticion atendida por: " + serverName + " ###";
        String cuerpo = encabezado + "\n\n" + datos;

        return ResponseEntity.ok()
                .header("X-Served-By", serverName)
                .body(cuerpo);
    }
}
