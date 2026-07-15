package com.powerresfot.examenfinal;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface InteraccionRepository extends JpaRepository<Interaccion, Integer> {

    @Query("select i from Interaccion i order by i.id asc")
    List<Interaccion> findAllOrderedById();
}
