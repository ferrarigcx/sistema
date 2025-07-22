const path = require('path');
const fs = require('fs-extra');
var ethers = require('ethers');

// RPCNODE details
const { tessera, besu } = require("../keys.js");
const host = besu.rpcnode.url;
const accountPrivateKey = besu.rpcnode.accountPrivateKey;

// abi and bytecode generated from simplestorage.sol:
// > solcjs --bin --abi simplestorage.sol
const contractJsonPath = path.resolve(__dirname, '../../','contracts','HashStorage.json');
const contractJson = JSON.parse(fs.readFileSync(contractJsonPath));
const contractAbi = contractJson.abi;
const contractBytecode = contractJson.evm.bytecode.object

// You need to use the accountAddress details provided to Quorum to send/interact with contracts
async function set(provider, wallet, deployedContractAbi, deployedContractAddress, value){
  const contract = new ethers.Contract(deployedContractAddress, deployedContractAbi, provider);
  const contractWithSigner = contract.connect(wallet);
  const tx = await contractWithSigner.saveHash(value);
  // verify the updated value
  await tx.wait();
  // const res = await contract.get();
  // console.log("Obtained value at deployed contract is: "+ res);
  return tx;
}

async function createContract( wallet, contractAbi, contractByteCode) {
  const factory = new ethers.ContractFactory(contractAbi, contractByteCode, wallet);
  const contract = await factory.deploy();
  // The contract is NOT deployed yet; we must wait until it is mined
  const deployed = await contract.waitForDeployment();
  //The contract is deployed now
  return contract
};

async function main(){
  const provider = new ethers.JsonRpcProvider(host);
  const wallet = new ethers.Wallet(accountPrivateKey, provider);
  const args = process.argv.slice(2);


  createContract(wallet, contractAbi, contractBytecode)
  .then(async function(contract){
    contractAddress = await contract.getAddress();
    console.log("Contract deployed at address: " + contractAddress);
    console.log("Evniando o Hash" )
    await set(provider, wallet, contractAbi, contractAddress, "0x4e944b578d55dc7f4e21f83f17b497c44d2bb3bcb2a1d2f37cf4297a2a6f3fdd");
    // await getAllPastEvents(host, contractAbi, tx.contractAddress);
  })
  .catch(console.error);

}

if (require.main === module) {
  main();
}

module.exports = exports = main