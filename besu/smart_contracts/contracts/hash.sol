// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

contract HashStorage {

    //var 
    bytes32 public storedHash;

    //tipo Console.log da minha var
    //var video, indexada;
    event video(
        bytes32 indexed storedHash
    );

    function saveHash(bytes32 _hash) public {
        storedHash = _hash;
        emit video(_hash);
    }
}
