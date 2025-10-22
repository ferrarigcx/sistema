const path = require('path');
const fs = require('fs-extra');
var ethers = require('ethers');

// RPCNODE details
const { tessera, besu } = require("../keys.js");
const host = besu.rpcnode.url;
const accountPrivateKey = besu.rpcnode.accountPrivateKey;

// abi and bytecode generated from simplestorage.sol:
// > solcjs --bin --abi simplestorage.sol
const contractJsonPath = path.resolve(__dirname, '../../', 'contracts', 'HashStorage.json');
const contractJson = JSON.parse(fs.readFileSync(contractJsonPath));
const contractAbi = contractJson.abi;
const contractBytecode = contractJson.evm.bytecode.object

// You need to use the accountAddress details provided to Quorum to send/interact with contracts
async function set(provider, wallet, deployedContractAbi, deployedContractAddress, value) {
  const contract = new ethers.Contract(deployedContractAddress, deployedContractAbi, provider);
  const contractWithSigner = contract.connect(wallet);
  const tx = await contractWithSigner.saveHash(value);
  // verify the updated value
  await tx.wait();
  console.log(tx);
}

async function main(value, contract) {

  const provider = new ethers.JsonRpcProvider(host);
  const wallet = new ethers.Wallet(accountPrivateKey, provider);
  const args = process.argv.slice(2);
  
  try {
    
    await set(provider, wallet, contractAbi, contract, value);
  
  } catch (error) {
  
    console.error;
  
  }


}

if (require.main === module) {
  main();
}

module.exports = exports = main