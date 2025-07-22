// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

contract HashStorage {
    bytes32 public storedHash;

    function saveHash(bytes32 _hash) public {
        storedHash = _hash;
    }
}
