// SPDX-License-Identifier: MIT
// Usar uma versão de compilador específica é uma boa prática de segurança.
pragma solidity ^0.8.10;

// Importando os "tijolos" de segurança da OpenZeppelin que instalamos.

contract NonConformityLedger{

    // --- Estruturas de Dados ---

    struct NonConformityRecord {
        uint256 id;
        bytes32 videoHash;      // Usar bytes32 para hashes é mais eficiente e seguro.
        uint256 timestamp;
        address registeredBy;   // Guarda quem registrou.
    }

    // --- Eventos ---

    // Um "recibo" público e pesquisável de que um registro foi feito.
    event NonConformityRegistered(

        uint256 indexed id,
        bytes32 indexed videoHash,
        address indexed registeredBy
    );

    // --- Variáveis de Estado (O "banco de dados" do contrato) ---

    mapping(uint256 => NonConformityRecord) public records;
    uint256 private recordCounter;

    // Esta é a lista das suas "chaves de segurança".
    // Um endereço é true se for autorizado, false caso contrário.
    mapping(address => bool) public authorizedAgents;


    // --- Modificadores (As Regras de Segurança) ---

    // Este modificador garante que apenas um agente autorizado possa chamar uma função.
    modifier onlyAuthorized() {
        // 'require' verifica uma condição. Se for falsa, a transação falha.
        require(authorizedAgents[msg.sender], "ACCESS_DENIED: Caller is not an authorized agent.");
        _; // Se a condição for verdadeira, o resto da função é executado.
    }


    // --- Funções ---

    /**
     * @dev O construtor define o Dono do contrato como a carteira que o implantou.
     * É herdado de Ownable.sol da OpenZeppelin.
   
    constructor() Ownable(msg.sender) {}

 
     * @notice ADMIN: Adiciona ou remove um endereço da lista de agentes autorizados.
     * @dev Apenas o Dono do contrato pode chamar esta função.
     
    function setAuthorizedAgent(address agentAddress, bool isAuthorized) public onlyOwner {
        authorizedAgents[agentAddress] = isAuthorized;
    }

     * @notice OPERACIONAL: Registra um novo hash de não conformidade.
     * @dev Só pode ser chamado por um agente autorizado.

    function registerNonConformity(bytes32 videoHash) public onlyAuthorized nonReentrant returns (uint256) {
        recordCounter++;
        uint256 newId = recordCounter;

        records[newId] = NonConformityRecord({
            id: newId,
            videoHash: videoHash,
            timestamp: block.timestamp, // Timestamp do bloco da blockchain (imutável).
            registeredBy: msg.sender    // msg.sender é o endereço que chamou a função.
        });

        emit NonConformityRegistered(newId, videoHash, msg.sender);

        return newId;
    }

     * @notice PÚBLICO: Permite que qualquer um consulte um registro pelo seu ID.
     * @dev Funções 'view' não custam gás para serem chamadas se feitas de fora da blockchain.
    
    function getRecordById(uint256 id) public view returns (NonConformityRecord memory) {
        return records[id];
    }
    */
}