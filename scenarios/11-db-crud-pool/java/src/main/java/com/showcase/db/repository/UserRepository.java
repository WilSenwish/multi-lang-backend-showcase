package com.showcase.db.repository;

import com.showcase.db.entity.User;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

/**
 * User Repository — Spring Data JPA
 *
 * 零实现代码！接口继承 JpaRepository，
 * Spring Data 自动生成 CRUD 实现 + 分页 + 排序
 */
@Repository
public interface UserRepository extends JpaRepository<User, Long> {
    // Spring Data JPA 方法命名查询（自动生成 SQL）
    Page<User> findByNameContaining(String keyword, Pageable pageable);
}
