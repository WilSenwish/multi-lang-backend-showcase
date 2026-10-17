package com.showcase.db.controller;

import com.showcase.db.entity.User;
import com.showcase.db.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/users")
public class UserController {

    @Autowired
    private UserRepository userRepository;

    // CREATE
    @PostMapping
    public ResponseEntity<?> create(@RequestBody UserInput input) {
        if (input.name == null || input.name.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "name is required"));
        }
        User user = new User();
        user.setName(input.name);
        user.setEmail(input.email);
        user.setAge(input.age);
        User saved = userRepository.save(user);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }

    // READ ONE
    @GetMapping("/{id}")
    public ResponseEntity<User> get(@PathVariable Long id) {
        return userRepository.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    // LIST (with pagination)
    @GetMapping
    public Map<String, Object> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        PageRequest pageable = PageRequest.of(page, size, Sort.by("id").ascending());
        Page<User> result = userRepository.findAll(pageable);

        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("items", result.getContent());
        resp.put("total", result.getTotalElements());
        resp.put("page", page);
        resp.put("size", size);
        return resp;
    }

    // UPDATE
    @PutMapping("/{id}")
    public ResponseEntity<User> update(@PathVariable Long id, @RequestBody UserInput input) {
        return userRepository.findById(id)
                .map(user -> {
                    if (input.name != null) user.setName(input.name);
                    if (input.email != null) user.setEmail(input.email);
                    if (input.age != null) user.setAge(input.age);
                    return ResponseEntity.ok(userRepository.save(user));
                })
                .orElse(ResponseEntity.notFound().build());
    }

    // DELETE
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        if (!userRepository.existsById(id)) {
            return ResponseEntity.notFound().build();
        }
        userRepository.deleteById(id);
        return ResponseEntity.noContent().build();
    }

    // DTO
    public static class UserInput {
        public String name;
        public String email;
        public Integer age;
    }
}
